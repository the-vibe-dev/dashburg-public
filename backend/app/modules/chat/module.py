from app.modules.base import BackendModule
from app.modules.chat.router import router

chat_module = BackendModule(
    key="chat",
    name="Chat",
    sidebar_label="Chat",
    router=router,
)
