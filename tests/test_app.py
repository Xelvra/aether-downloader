import asyncio
import contextlib

import pytest

import stahovac.app as app_mod


class TestMainCancellation:
    """Ctrl+C / shutdown nesmí při ukončení vyplivnout traceback z flet-webu.

    flet-web (``FletApp.__on_session_created``) po dokončení ``main()`` volá
    ``self.__session.after_event(...)``. Když je úloha session zrušena
    (Ctrl+C, shutdown) a ``main`` CancelledError spolkne, vrátí se normálně,
    flet-web pokračuje na už zrušenou (None) session a zaloguje
    ``AttributeError: 'NoneType' object has no attribute 'after_event'``.
    """

    def test_main_propagates_cancellation(self, monkeypatch):
        monkeypatch.setattr(app_mod, "GuiApp", lambda page: None)

        async def scenario():
            task = asyncio.create_task(app_mod.main(None))
            await asyncio.sleep(0.01)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())

    def test_no_traceback_after_cancel_with_disposed_session(self, monkeypatch):
        monkeypatch.setattr(app_mod, "GuiApp", lambda page: None)
        after_event_calls = []

        class FakeSession:
            page = None

            def after_event(self, page):
                after_event_calls.append(1)

        class FakeApp:
            """Napodobuje chování ``FletApp.__on_session_created`` (flet-web)."""

            def __init__(self):
                self._session = FakeSession()

            def dispose(self):
                self._session = None

            async def on_session_created(self):
                try:
                    await app_mod.main(self._session)
                    await self._session.after_event(self._session.page)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    raise AssertionError(
                        f"flet-web po zrušení session zaloguje chybu: {type(exc).__name__}: {exc}"
                    ) from exc

        async def scenario():
            fapp = FakeApp()
            task = asyncio.create_task(fapp.on_session_created())
            await asyncio.sleep(0.01)
            fapp.dispose()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            assert after_event_calls == []

        asyncio.run(scenario())
