import discord
import ollama
import argparse
import asyncio
import os
import random

from search import search
from dotenv import load_dotenv

load_dotenv()

parser = argparse.ArgumentParser()
parser.add_argument('--maintenance', action='store_true')
parser.add_argument('--debug', action='store_true')
args = parser.parse_args()

class MyClient(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_queue = asyncio.Queue()
        self.worker_task = None
        self.maintenance_messages = [
            "I'm currently under maintenance. Should be back up soon! Thanks for waiting!",
            "I'm being updated rn... pls be patient, ty!",
            "Go touch some grass while I'm going through maintenance",
            "Hi :D. you should wait until i'm done being maintained."
        ]

    async def setup_hook(self):
        self.worker_task = asyncio.create_task(self.queue_worker())

    async def queue_worker(self):
        while True:
            message, messages_payload = await self.request_queue.get()

            try:
                async with message.channel.typing():
                    final_content = None
                    
                    while True:
                        response = await asyncio.to_thread(
                            ollama.chat,
                            model=os.getenv("MODEL"),
                            messages=messages_payload,
                            tools=[search] # Function passed here
                        )

                        messages_payload.append(response.message)
                        
                        if not response.message.tool_calls:
                            final_content = response.message.content
                            break
                        
                        for tool in response.message.tool_calls:
                            function_name = tool.function.name
                            function_args = tool.function.arguments
                            
                            if function_name == 'search':
                                tool_result = await asyncio.to_thread(
                                    search, 
                                    **function_args
                                )
                                
                                messages_payload.append({
                                    'role': 'tool',
                                    'content': str(tool_result),
                                    'name': function_name, 
                                })

                    # 5. Send the final response to Discord
                    if args.debug:
                        await message.reply(f"Debug: {response}")

                    if final_content:
                        # Split long messages if necessary (Discord 2000 char limit)
                        await message.reply(final_content[0:2000])
                        for i in range(2000, len(final_content), 2000):
                            await message.channel.send(final_content[i:i+2000])

            except Exception as e:
                await message.reply(f"Error: {e}")

            self.request_queue.task_done()

    async def on_message(self, message: discord.Message):
        if (f"<@{self.user.id}>" not in message.content):
            lookahead_msg = await message.channel.fetch_message(message.reference.message_id)
            if not (lookahead_msg and lookahead_msg.author == self.user): return
        elif message.author == self.user: return

        if args.maintenance:
            await message.reply(random.choice(self.maintenance_messages))
            return

        messages = []
        current_msg = message

        while current_msg:
            if current_msg.author == self.user:
                messages.insert(0, {
                    'role': 'assistant',
                    'content': current_msg.content
                })
            else:
                messages.insert(0, {
                    'role': 'user',
                    'content': current_msg.content.replace(f"<@{self.user.id}>", "")
                })

            if current_msg.reference and current_msg.reference.message_id:
                try:
                    current_msg = await message.channel.fetch_message(current_msg.reference.message_id)
                except:
                    break
            else:
                break

        messages.insert(0, {
            'role': 'system',
            'content': 'Do not use markdown tables or LaTeX because they are unsupported (any other markdown is fine; you are allowed to use any formating during and only during thinking). Also, be concise with your response. There is no need to overthink or overdo anything. If a query seems to require search (real-time information), use the search tool.'
        })

        await self.request_queue.put((message, messages))


intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(os.getenv("BOT_KEY"))