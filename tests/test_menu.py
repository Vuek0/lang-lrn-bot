from aiogram.types import Chat, Message, User

from bot import menu


def _msg(text: str) -> Message:
    return Message(message_id=1, date=0, chat=Chat(id=1, type="private"),
                   from_user=User(id=1, is_bot=False, first_name="U"), text=text)


def test_keyboard_layout():
    kb = menu.main_keyboard()
    assert [[b.text for b in row] for row in kb.keyboard] == [
        [menu.REVIEW, menu.WORDS], [menu.STATS, menu.PERSONA], [menu.PRACTICE, menu.MORE],
    ]
    assert kb.is_persistent and kb.resize_keyboard and kb.input_field_placeholder


def test_menu_buttons_are_not_free_text():
    assert not menu.NOT_MENU.resolve(_msg(menu.REVIEW))
    assert menu.NOT_MENU.resolve(_msg("casa"))
