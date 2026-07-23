import json
import shutil
from typing import List, Optional, Tuple

from app.domain.docker import (
    ActionResponse,
    ComposeServiceStatus,
    ComposeStatusResponse,
    DockerContainer,
    DockerContainerDetail,
    DockerContainerListResponse,
    DockerInfoResponse,
    DockerLogsResponse,
)
from app.utils.run_command import run_command


def docker_installed() -> bool:
    return shutil.which("docker") is not None


def get_docker_info() -> DockerInfoResponse:
    if not docker_installed():
        return DockerInfoResponse(installed=False, running=False, message="docker CLI not found")

    version_out, _, version_rc = run_command(["docker", "version", "--format", "{{.Server.Version}}"])
    info_out, info_err, info_rc = run_command(["docker", "info", "--format", "{{json .}}"], timeout=20)
    if info_rc != 0:
        return DockerInfoResponse(
            installed=True,
            running=False,
            version=version_out or None,
            message=info_err or "Docker daemon is not running",
        )

    try:
        info = json.loads(info_out)
    except json.JSONDecodeError:
        info = {}

    return DockerInfoResponse(
        installed=True,
        running=True,
        version=version_out or info.get("ServerVersion"),
        containers_running=info.get("ContainersRunning"),
        containers_total=info.get("Containers"),
    )


def list_containers(
    all_containers: bool = True,
    filter_text: Optional[str] = None,
) -> Tuple[DockerContainerListResponse, Optional[str]]:
    if not docker_installed():
        return DockerContainerListResponse(containers=[]), "docker CLI not found"

    cmd = ["docker", "ps"]
    if all_containers:
        cmd.append("-a")
    cmd.extend(["--format", "{{json .}}"])
    stdout, stderr, rc = run_command(cmd, timeout=20)
    if rc != 0:
        return DockerContainerListResponse(containers=[]), stderr or "Could not list containers"

    containers: List[DockerContainer] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = (item.get("Names") or "").lstrip("/")
        container = DockerContainer(
            id=item.get("ID") or item.get("Id") or "",
            name=name,
            image=item.get("Image") or "",
            status=item.get("Status") or "",
            state=item.get("State") or "",
            ports=item.get("Ports") or "",
            created=item.get("CreatedAt") or item.get("RunningFor"),
        )
        containers.append(container)

    if filter_text:
        needle = filter_text.lower()
        containers = [
            container
            for container in containers
            if needle in container.name.lower()
            or needle in container.image.lower()
            or needle in container.status.lower()
        ]
    return DockerContainerListResponse(containers=containers), None


def get_container_status(name_or_id: str) -> Tuple[Optional[DockerContainerDetail], Optional[str]]:
    if not docker_installed():
        return None, "docker CLI not found"

    stdout, stderr, rc = run_command(["docker", "inspect", name_or_id, "--format", "{{json .}}"], timeout=20)
    if rc != 0:
        return None, stderr or "Container not found"

    try:
        item = json.loads(stdout)
    except json.JSONDecodeError:
        return None, "Could not parse docker inspect output"

    state = item.get("State") or {}
    config = item.get("Config") or {}
    names = item.get("Name", "").lstrip("/")
    ports: List[str] = []
    port_map = item.get("NetworkSettings", {}).get("Ports") or {}
    for container_port, bindings in port_map.items():
        if not bindings:
            ports.append(container_port)
            continue
        for binding in bindings:
            host_ip = binding.get("HostIp") or "0.0.0.0"
            host_port = binding.get("HostPort")
            ports.append(f"{host_ip}:{host_port}->{container_port}")

    health = None
    health_info = state.get("Health") or {}
    if health_info:
        health = health_info.get("Status")

    return (
        DockerContainerDetail(
            id=item.get("Id", "")[:12],
            name=names,
            image=config.get("Image") or "",
            status=state.get("Status") or "",
            state="running" if state.get("Running") else "stopped",
            health=health,
            ports=ports,
            started_at=state.get("StartedAt"),
            finished_at=state.get("FinishedAt"),
        ),
        None,
    )


def get_container_logs(name_or_id: str, lines: int = 100) -> Tuple[Optional[DockerLogsResponse], Optional[str]]:
    if not docker_installed():
        return None, "docker CLI not found"

    stdout, stderr, rc = run_command(
        ["docker", "logs", "--tail", str(lines), name_or_id],
        timeout=20,
    )
    if rc != 0:
        return None, stderr or "Could not read container logs"
    return DockerLogsResponse(container=name_or_id, lines=stdout.splitlines()), None


def container_action(name_or_id: str, action: str) -> Tuple[ActionResponse, Optional[str]]:
    if not docker_installed():
        return ActionResponse(success=False, message="docker CLI not found"), "docker CLI not found"

    if action == "start":
        detail, _ = get_container_status(name_or_id)
        if detail and detail.state == "running":
            return ActionResponse(success=True, message=f"Container {name_or_id} is already running."), None

    if action == "stop":
        detail, _ = get_container_status(name_or_id)
        if detail and detail.state == "stopped":
            return ActionResponse(success=True, message=f"Container {name_or_id} is already stopped."), None

    stdout, stderr, rc = run_command(["docker", action, name_or_id], timeout=30)
    if rc != 0:
        detail = stderr or stdout or f"Could not {action} container"
        return ActionResponse(success=False, message=detail), detail
    return ActionResponse(success=True, message=f"Container {name_or_id} {action}ed."), None


def compose_status(
    project_directory: Optional[str] = None,
    project: Optional[str] = None,
) -> Tuple[ComposeStatusResponse, Optional[str]]:
    if not docker_installed():
        return ComposeStatusResponse(services=[]), "docker CLI not found"

    cmd = ["docker", "compose"]
    if project_directory:
        cmd.extend(["--project-directory", project_directory])
    if project:
        cmd.extend(["--project-name", project])
    cmd.extend(["ps", "--format", "json"])

    stdout, stderr, rc = run_command(cmd, timeout=20)
    if rc != 0:
        return ComposeStatusResponse(project=project, services=[]), stderr or "Could not list compose services"

    services: List[ComposeServiceStatus] = []
    if stdout.strip():
        try:
            payload = json.loads(stdout)
            rows = payload if isinstance(payload, list) else [payload]
        except json.JSONDecodeError:
            rows = []
            for line in stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        for item in rows:
            services.append(
                ComposeServiceStatus(
                    name=item.get("Name") or item.get("Service") or "",
                    state=item.get("State") or "",
                    status=item.get("Status") or "",
                    ports=item.get("Ports") or item.get("Publishers") or "",
                )
            )
    return ComposeStatusResponse(project=project, services=services), None
