.
├── AGENTS.md
├── app
│   ├── agent
│   │   ├── agent.py
│   │   ├── credentials.py
│   │   ├── envutil.py
│   │   ├── helpers.py
│   │   ├── __init__.py
│   │   ├── local_auth.py
│   │   ├── loop.py
│   │   ├── pairing.py
│   │   ├── __pycache__
│   │   │   ├── agent.cpython-313.pyc
│   │   │   ├── credentials.cpython-313.pyc
│   │   │   ├── envutil.cpython-313.pyc
│   │   │   ├── helpers.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── local_auth.cpython-313.pyc
│   │   │   ├── loop.cpython-313.pyc
│   │   │   ├── pairing.cpython-313.pyc
│   │   │   └── tunnel.cpython-313.pyc
│   │   └── tunnel.py
│   ├── auth.py
│   ├── cli.py
│   ├── db
│   │   ├── audit_log.py
│   │   ├── capabilities.py
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── pending_actions.py
│   │   └── __pycache__
│   │       ├── audit_log.cpython-313.pyc
│   │       ├── capabilities.cpython-313.pyc
│   │       ├── __init__.cpython-313.pyc
│   │       ├── models.cpython-313.pyc
│   │       └── pending_actions.cpython-313.pyc
│   ├── dependencies.py
│   ├── domain
│   │   ├── admin.py
│   │   ├── alerts.py
│   │   ├── assistant.py
│   │   ├── audio.py
│   │   ├── capabilities.py
│   │   ├── clipboard.py
│   │   ├── display.py
│   │   ├── docker.py
│   │   ├── exceptions.py
│   │   ├── filesystem.py
│   │   ├── __init__.py
│   │   ├── input_control.py
│   │   ├── maintenance.py
│   │   ├── media.py
│   │   ├── monitoring.py
│   │   ├── network.py
│   │   ├── notifications.py
│   │   ├── power.py
│   │   ├── processes.py
│   │   ├── push.py
│   │   ├── __pycache__
│   │   │   ├── admin.cpython-313.pyc
│   │   │   ├── alerts.cpython-313.pyc
│   │   │   ├── assistant.cpython-313.pyc
│   │   │   ├── audio.cpython-313.pyc
│   │   │   ├── capabilities.cpython-313.pyc
│   │   │   ├── clipboard.cpython-313.pyc
│   │   │   ├── display.cpython-313.pyc
│   │   │   ├── docker.cpython-313.pyc
│   │   │   ├── filesystem.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── input_control.cpython-313.pyc
│   │   │   ├── maintenance.cpython-313.pyc
│   │   │   ├── media.cpython-313.pyc
│   │   │   ├── monitoring.cpython-313.pyc
│   │   │   ├── network.cpython-313.pyc
│   │   │   ├── notifications.cpython-313.pyc
│   │   │   ├── power.cpython-313.pyc
│   │   │   ├── processes.cpython-313.pyc
│   │   │   ├── push.cpython-313.pyc
│   │   │   ├── scheduler.cpython-313.pyc
│   │   │   ├── spotify.cpython-313.pyc
│   │   │   └── system_info.cpython-313.pyc
│   │   ├── scheduler.py
│   │   ├── security.py
│   │   ├── spotify.py
│   │   └── system_info.py
│   ├── __init__.py
│   ├── main.py
│   ├── middleware.py
│   ├── prompts.py
│   ├── __pycache__
│   │   ├── auth.cpython-313.pyc
│   │   ├── cli.cpython-313.pyc
│   │   ├── dependencies.cpython-313.pyc
│   │   ├── __init__.cpython-313.pyc
│   │   ├── main.cpython-313.pyc
│   │   ├── middleware.cpython-313.pyc
│   │   ├── prompts.cpython-313.pyc
│   │   ├── rate_limiter.cpython-313.pyc
│   │   └── setup_cli.cpython-313.pyc
│   ├── rate_limiter.py
│   ├── routers
│   │   ├── admin.py
│   │   ├── alerts.py
│   │   ├── assistant.py
│   │   ├── audio.py
│   │   ├── capabilities.py
│   │   ├── clipboard.py
│   │   ├── display.py
│   │   ├── docker.py
│   │   ├── filesystem.py
│   │   ├── __init__.py
│   │   ├── input_control.py
│   │   ├── maintenance.py
│   │   ├── media.py
│   │   ├── monitoring.py
│   │   ├── network.py
│   │   ├── notifications.py
│   │   ├── power.py
│   │   ├── processes.py
│   │   ├── push.py
│   │   ├── __pycache__
│   │   │   ├── admin.cpython-313.pyc
│   │   │   ├── alerts.cpython-313.pyc
│   │   │   ├── assistant.cpython-313.pyc
│   │   │   ├── audio.cpython-313.pyc
│   │   │   ├── capabilities.cpython-313.pyc
│   │   │   ├── clipboard.cpython-313.pyc
│   │   │   ├── display.cpython-313.pyc
│   │   │   ├── docker.cpython-313.pyc
│   │   │   ├── filesystem.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── input_control.cpython-313.pyc
│   │   │   ├── maintenance.cpython-313.pyc
│   │   │   ├── media.cpython-313.pyc
│   │   │   ├── monitoring.cpython-313.pyc
│   │   │   ├── network.cpython-313.pyc
│   │   │   ├── notifications.cpython-313.pyc
│   │   │   ├── power.cpython-313.pyc
│   │   │   ├── processes.cpython-313.pyc
│   │   │   ├── push.cpython-313.pyc
│   │   │   ├── registry.cpython-313.pyc
│   │   │   ├── scheduler.cpython-313.pyc
│   │   │   ├── security.cpython-313.pyc
│   │   │   ├── spotify.cpython-313.pyc
│   │   │   └── system_info.cpython-313.pyc
│   │   ├── registry.py
│   │   ├── scheduler.py
│   │   ├── security.py
│   │   ├── spotify.py
│   │   └── system_info.py
│   ├── services
│   │   ├── alert_delivery.py
│   │   ├── alert_history.py
│   │   ├── alerts.py
│   │   ├── assistant
│   │   │   ├── gatekeeper_tools.py
│   │   │   ├── helpers.py
│   │   │   ├── images.py
│   │   │   ├── __init__.py
│   │   │   ├── prompts.py
│   │   │   ├── __pycache__
│   │   │   │   ├── gatekeeper_tools.cpython-313.pyc
│   │   │   │   ├── helpers.cpython-313.pyc
│   │   │   │   ├── images.cpython-313.pyc
│   │   │   │   ├── __init__.cpython-313.pyc
│   │   │   │   ├── safety.cpython-313.pyc
│   │   │   │   ├── session.cpython-313.pyc
│   │   │   │   ├── stream.cpython-313.pyc
│   │   │   │   ├── tool_exec.cpython-313.pyc
│   │   │   │   ├── tools.cpython-313.pyc
│   │   │   │   └── workflow.cpython-313.pyc
│   │   │   ├── safety.py
│   │   │   ├── session.py
│   │   │   ├── stream.py
│   │   │   ├── tool_exec.py
│   │   │   ├── tools.py
│   │   │   └── workflow.py
│   │   ├── audio.py
│   │   ├── audit.py
│   │   ├── capabilities.py
│   │   ├── clipboard.py
│   │   ├── display.py
│   │   ├── docker.py
│   │   ├── filesystem.py
│   │   ├── gatekeeper
│   │   │   ├── client.py
│   │   │   ├── __init__.py
│   │   │   └── __pycache__
│   │   │       ├── client.cpython-313.pyc
│   │   │       └── __init__.cpython-313.pyc
│   │   ├── __init__.py
│   │   ├── input_control.py
│   │   ├── maintenance.py
│   │   ├── maintenance_tasks.py
│   │   ├── media.py
│   │   ├── monitoring.py
│   │   ├── network.py
│   │   ├── notifications.py
│   │   ├── power.py
│   │   ├── processes.py
│   │   ├── push.py
│   │   ├── __pycache__
│   │   │   ├── alert_delivery.cpython-313.pyc
│   │   │   ├── alert_history.cpython-313.pyc
│   │   │   ├── alerts.cpython-313.pyc
│   │   │   ├── audio.cpython-313.pyc
│   │   │   ├── audit.cpython-313.pyc
│   │   │   ├── capabilities.cpython-313.pyc
│   │   │   ├── clipboard.cpython-313.pyc
│   │   │   ├── display.cpython-313.pyc
│   │   │   ├── docker.cpython-313.pyc
│   │   │   ├── filesystem.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── maintenance.cpython-313.pyc
│   │   │   ├── maintenance_tasks.cpython-313.pyc
│   │   │   ├── media.cpython-313.pyc
│   │   │   ├── monitoring.cpython-313.pyc
│   │   │   ├── network.cpython-313.pyc
│   │   │   ├── notifications.cpython-313.pyc
│   │   │   ├── power.cpython-313.pyc
│   │   │   ├── processes.cpython-313.pyc
│   │   │   ├── push.cpython-313.pyc
│   │   │   ├── relay_status.cpython-313.pyc
│   │   │   ├── scheduler.cpython-313.pyc
│   │   │   ├── security.cpython-313.pyc
│   │   │   ├── spotify.cpython-313.pyc
│   │   │   └── system_info.cpython-313.pyc
│   │   ├── relay_status.py
│   │   ├── scheduler.py
│   │   ├── security.py
│   │   ├── spotify.py
│   │   └── system_info.py
│   ├── setup
│   │   ├── cli_links.py
│   │   ├── credentials.py
│   │   ├── deps.py
│   │   ├── flow.py
│   │   ├── __init__.py
│   │   ├── preflight.py
│   │   ├── __pycache__
│   │   │   ├── cli_links.cpython-313.pyc
│   │   │   ├── credentials.cpython-313.pyc
│   │   │   ├── deps.cpython-313.pyc
│   │   │   ├── flow.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── preflight.cpython-313.pyc
│   │   │   ├── services.cpython-313.pyc
│   │   │   ├── wizard.cpython-313.pyc
│   │   │   └── writers.cpython-313.pyc
│   │   ├── services.py
│   │   ├── wizard.py
│   │   └── writers.py
│   ├── setup_cli.py
│   ├── ui
│   │   ├── admin_dashboard_page.py
│   │   ├── __init__.py
│   │   ├── pairing_browser.py
│   │   ├── pairing_page.py
│   │   ├── __pycache__
│   │   │   ├── admin_dashboard_page.cpython-313.pyc
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── pairing_browser.cpython-313.pyc
│   │   │   ├── pairing_page.cpython-313.pyc
│   │   │   └── setup_wizard_page.cpython-313.pyc
│   │   └── setup_wizard_page.py
│   └── utils
│       ├── config.py
│       ├── desktop_env.py
│       ├── emails
│       │   ├── __init__.py
│       │   └── __pycache__
│       │       └── __init__.cpython-313.pyc
│       ├── env_paths.py
│       ├── env_template.py
│       ├── errors.py
│       ├── __init__.py
│       ├── input_header.py
│       ├── __pycache__
│       │   ├── config.cpython-313.pyc
│       │   ├── desktop_env.cpython-313.pyc
│       │   ├── env_paths.cpython-313.pyc
│       │   ├── env_template.cpython-313.pyc
│       │   ├── errors.cpython-313.pyc
│       │   ├── __init__.cpython-313.pyc
│       │   ├── input_header.cpython-313.pyc
│       │   └── run_command.cpython-313.pyc
│       ├── run_command.py
│       └── spotify_client.py
├── audit_log.sqlite
├── capabilities.sqlite
├── config.yaml
├── dist
│   ├── mikesplore_vela-1.0.0-py3-none-any.whl
│   └── mikesplore_vela-1.0.0.tar.gz
├── doc
│   ├── API_DOCUMENTATION.md
│   ├── DEVTO_README.md
│   ├── HOW_IT_WORKS.md
│   └── spotifyrecommended.py
├── installer.py
├── migrate_vela.sh
├── mikesplore_vela.egg-info
│   ├── dependency_links.txt
│   ├── entry_points.txt
│   ├── PKG-INFO
│   ├── requires.txt
│   ├── SOURCES.txt
│   └── top_level.txt
├── pending_actions.sqlite
├── ProjectTree.md
├── __pycache__
│   └── installer.cpython-313.pyc
├── pyproject.toml
├── README.md
├── remotepc.service
├── requirements.txt
├── run.py
├── scheduler_jobs.sqlite
├── setup.sh
├── tests
│   ├── conftest.py
│   ├── db
│   │   └── __init__.py
│   ├── __pycache__
│   │   ├── conftest.cpython-313-pytest-9.0.3.pyc
│   │   ├── conftest.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_admin_audit.cpython-313.pyc
│   │   ├── test_admin_audit.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_agent_tunnel.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_agent_tunnel.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_alert_history.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_alert_history.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_alert_scheduling.cpython-313.pyc
│   │   ├── test_alert_scheduling.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_conditional.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_download.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_helpers.cpython-313.pyc
│   │   ├── test_assistant_helpers.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_images.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_stream_gate_labels.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_assistant_stream_gate_labels.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_tool_exec.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant_workflow.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_audio.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_auth.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_capabilities.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_capabilities.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_cli.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_clipboard.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_desktop_applications.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_desktop_applications.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_display.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_emails.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_env_template.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_env_template.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_error_handling.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_filesystem.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_gatekeeper_integration.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_input_control.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_maintenance.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_maintenance_services.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_media.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_monitoring.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_network_cache.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_network_cache.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_network.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_network_location.cpython-313-pytest-9.0.3.pyc
│   │   ├── test_network_location.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_notifications.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_ping.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_power.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_processes.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_router_registry.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_scheduler.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_security.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_service_monitoring.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_setup_dependencies.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_spotify_service.cpython-313-pytest-9.1.1.pyc
│   │   └── test_system_info.cpython-313-pytest-9.1.1.pyc
│   ├── routers
│   │   ├── __init__.py
│   │   ├── __pycache__
│   │   │   ├── __init__.cpython-313.pyc
│   │   │   ├── test_assistant.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_audio.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_auth.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_clipboard.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_display.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_docker.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_error_handling.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_filesystem.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_input_control.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_maintenance.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_media.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_monitoring.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_network.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_network_diagnostics.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_notifications.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_ping.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_power.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_processes_apps.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_processes.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_scheduler.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_security.cpython-313-pytest-9.1.1.pyc
│   │   │   ├── test_spotify.cpython-313-pytest-9.1.1.pyc
│   │   │   └── test_system_info.cpython-313-pytest-9.1.1.pyc
│   │   ├── test_assistant.py
│   │   ├── test_audio.py
│   │   ├── test_auth.py
│   │   ├── test_clipboard.py
│   │   ├── test_display.py
│   │   ├── test_docker.py
│   │   ├── test_error_handling.py
│   │   ├── test_filesystem.py
│   │   ├── test_input_control.py
│   │   ├── test_maintenance.py
│   │   ├── test_media.py
│   │   ├── test_monitoring.py
│   │   ├── test_network_diagnostics.py
│   │   ├── test_network.py
│   │   ├── test_notifications.py
│   │   ├── test_ping.py
│   │   ├── test_power.py
│   │   ├── test_processes_apps.py
│   │   ├── test_processes.py
│   │   ├── test_scheduler.py
│   │   ├── test_security.py
│   │   ├── test_spotify.py
│   │   └── test_system_info.py
│   ├── services
│   │   ├── assistant
│   │   │   └── __init__.py
│   │   └── __init__.py
│   ├── test_admin_audit.py
│   ├── test_agent_tunnel.py
│   ├── test_alert_history.py
│   ├── test_alert_scheduling.py
│   ├── test_assistant_conditional.py
│   ├── test_assistant_download.py
│   ├── test_assistant_helpers.py
│   ├── test_assistant_images.py
│   ├── test_assistant.py
│   ├── test_assistant_stream_gate_labels.py
│   ├── test_assistant_workflow.py
│   ├── test_audio.py
│   ├── test_auth.py
│   ├── test_capabilities.py
│   ├── test_clipboard.py
│   ├── test_cli.py
│   ├── test_desktop_applications.py
│   ├── test_display.py
│   ├── test_emails.py
│   ├── test_env_template.py
│   ├── test_error_handling.py
│   ├── test_filesystem.py
│   ├── test_gatekeeper_integration.py
│   ├── test_input_control.py
│   ├── test_maintenance.py
│   ├── test_maintenance_services.py
│   ├── test_media.py
│   ├── test_monitoring.py
│   ├── test_network_cache.py
│   ├── test_network_location.py
│   ├── test_network.py
│   ├── test_notifications.py
│   ├── test_ping.py
│   ├── test_power.py
│   ├── test_processes.py
│   ├── test_router_registry.py
│   ├── test_scheduler.py
│   ├── test_security.py
│   ├── test_service_monitoring.py
│   ├── test_setup_dependencies.py
│   ├── test_spotify_service.py
│   └── test_system_info.py
└── vela.egg-info
    ├── dependency_links.txt
    ├── entry_points.txt
    ├── PKG-INFO
    ├── requires.txt
    ├── SOURCES.txt
    └── top_level.txt

37 directories, 447 files
