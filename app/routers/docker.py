from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_current_user
from app.domain.docker import (
    ActionResponse,
    ComposeStatusResponse,
    DockerContainerDetail,
    DockerContainerListResponse,
    DockerInfoResponse,
    DockerLogsResponse,
)
from app.services import docker as docker_service

router = APIRouter(prefix="/docker", tags=["docker"])


@router.get("/info", response_model=DockerInfoResponse, dependencies=[Depends(get_current_user)])
async def docker_info() -> Any:
    """Return Docker installation and daemon status."""
    return docker_service.get_docker_info()


@router.get("/containers", response_model=DockerContainerListResponse, dependencies=[Depends(get_current_user)])
async def list_containers(
    all: bool = Query(True, description="Include stopped containers"),
    filter: str | None = Query(None, description="Filter by container name, image, or status"),
) -> Any:
    """List Docker containers."""
    response, error = docker_service.list_containers(all_containers=all, filter_text=filter)
    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.get("/containers/{name_or_id}", response_model=DockerContainerDetail, dependencies=[Depends(get_current_user)])
async def container_status(name_or_id: str) -> Any:
    """Get detailed status for one Docker container."""
    detail, error = docker_service.get_container_status(name_or_id)
    if error or not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error or "Container not found")
    return detail


@router.get("/containers/{name_or_id}/logs", response_model=DockerLogsResponse, dependencies=[Depends(get_current_user)])
async def container_logs(
    name_or_id: str,
    lines: int = Query(100, ge=1, le=1000),
) -> Any:
    """Get recent logs for a Docker container."""
    logs, error = docker_service.get_container_logs(name_or_id, lines=lines)
    if error or not logs:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error or "Could not read logs")
    return logs


@router.post("/containers/{name_or_id}/start", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def start_container(name_or_id: str) -> Any:
    """Start a Docker container."""
    response, error = docker_service.container_action(name_or_id, "start")
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.post("/containers/{name_or_id}/stop", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def stop_container(name_or_id: str) -> Any:
    """Stop a Docker container."""
    response, error = docker_service.container_action(name_or_id, "stop")
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.post("/containers/{name_or_id}/restart", response_model=ActionResponse, dependencies=[Depends(get_current_user)])
async def restart_container(name_or_id: str) -> Any:
    """Restart a Docker container."""
    response, error = docker_service.container_action(name_or_id, "restart")
    if error and not response.success:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response


@router.get("/compose", response_model=ComposeStatusResponse, dependencies=[Depends(get_current_user)])
async def compose_status(
    project_directory: str | None = Query(None),
    project: str | None = Query(None),
) -> Any:
    """List services from a Docker Compose project."""
    response, error = docker_service.compose_status(project_directory=project_directory, project=project)
    if error:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error)
    return response
