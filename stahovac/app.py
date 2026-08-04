import asyncio

from stahovac.gui.app import GuiApp


async def main(page):
    GuiApp(page)
    # Smyčka drží session naživu. CancelledError se NESPOLKNUTÁ – při ukončení
    # (Ctrl+C / shutdown) se musí propagovat dál. Když se zrušená úloha vrátí
    # normálně, flet-web v __on_session_created() ještě zavolá
    # self.__session.after_event() na už zrušenou (None) session a při ukončení
    # vypíše traceback: AttributeError: 'NoneType' object has no attribute
    # 'after_event'.
    while True:
        await asyncio.sleep(3600)
