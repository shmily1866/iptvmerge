import asyncio

async def run():
    try:
        p = await asyncio.create_subprocess_exec(
            'ffmpeg', '-version',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        print("success")
    except Exception as e:
        print(f"Error type: {type(e)}")
        print(f"Error str: '{str(e)}'")
        import traceback
        traceback.print_exc()

asyncio.run(run())
