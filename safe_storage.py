from aiogram.contrib.fsm_storage.memory import MemoryStorage

class SafeMemoryStorage(MemoryStorage):
    async def reset_state(self, *, chat: int = None, user: int = None, with_data: bool = True):
        if chat is not None and user is not None:
            data = self.data.get(chat, {})
            if user in data:
                await super().reset_state(chat=chat, user=user, with_data=with_data)

def _cleanup(self, chat, user):
    chat_id = str(chat)
    user_id = str(user)
    if chat_id in self.data and user_id in self.data[chat_id]:
        if self.data[chat_id][user_id] == {'state': None, 'data': {}, 'bucket': {}}:
            del self.data[chat_id][user_id]
            if not self.data[chat_id]:
                del self.data[chat_id]