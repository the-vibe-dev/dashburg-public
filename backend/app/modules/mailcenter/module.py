from app.modules.base import BackendModule
from app.modules.mailcenter.router import router

mailcenter_module = BackendModule(
    key="mailcenter",
    name="MailCenter",
    sidebar_label="MailCenter",
    router=router,
    routes=[
        {"path": "/modules/mailcenter", "label": "MailCenter"},
    ],
    cards=[
        {
            "title": "MailCenter",
            "description": "Operational console for inbound/outbound mail, threads, routing status, and subsystem activity.",
            "href": "/modules/mailcenter",
        }
    ],
)
