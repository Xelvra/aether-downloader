import asyncio

from stahovac.gui.app import GuiApp


async def main(page):
    GuiApp(page)
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
