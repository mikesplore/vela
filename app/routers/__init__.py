from .audio import router as audio_router
from .clipboard import router as clipboard_router
from .display import router as display_router
from .filesystem import router as filesystem_router
from .input_control import router as input_control_router
from .maintenance import router as maintenance_router
from .media import router as media_router
from .monitoring import router as monitoring_router
from .network import router as network_router
from .notifications import router as notifications_router
from .power import router as power_router
from .processes import router as processes_router
from .scheduler import router as scheduler_router
from .security import router as security_router
from .system_info import router as system_info_router
from .assistant import router as assistant_router
from .assistant import router as assistant_stream_router

all_routers = [
    display_router,
    audio_router,
    power_router,
    notifications_router,
    network_router,
    filesystem_router,
    input_control_router,
    system_info_router,
    monitoring_router,
    processes_router,
    security_router,
    scheduler_router,
    maintenance_router,
    media_router,
    clipboard_router,
    assistant_router,
    assistant_stream_router,
]
