"""离线包管理服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import (
    OfflinePackage,
    PackageStatus,
)
from app.repositories import OfflinePackageRepository


# 仓储实例
_repo = OfflinePackageRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_packages(
    status: Optional[str] = None,
    target_device: Optional[str] = None,
    limit: int = 100,
) -> list[OfflinePackage]:
    """获取离线包列表。"""
    packages = await _repo.find_all(status, target_device, limit)
    return [OfflinePackage(**p) for p in packages]


async def get_package(package_id: str) -> Optional[OfflinePackage]:
    """获取离线包详情。"""
    package = await _repo.find_by_id(package_id)
    if package:
        return OfflinePackage(**package)
    return None


async def create_package(package: OfflinePackage) -> OfflinePackage:
    """创建离线包。"""
    package.id = _generate_id()
    package.created_at = datetime.utcnow()
    package.updated_at = datetime.utcnow()
    package.status = PackageStatus.BUILDING

    await _repo.create(package.model_dump())
    return package


async def update_package(
    package_id: str,
    updates: dict[str, Any]
) -> Optional[OfflinePackage]:
    """更新离线包。"""
    package = await get_package(package_id)
    if not package:
        return None

    for key, value in updates.items():
        if hasattr(package, key):
            setattr(package, key, value)

    package.updated_at = datetime.utcnow()
    await _repo.update(package_id, package.model_dump())
    return package


async def delete_package(package_id: str) -> bool:
    """删除离线包。"""
    return await _repo.delete_one({"id": package_id})


async def build_package(package_id: str) -> Optional[OfflinePackage]:
    """构建离线包。"""
    package = await get_package(package_id)
    if not package:
        return None

    package.status = PackageStatus.BUILDING
    package.build_started_at = datetime.utcnow()
    package.updated_at = datetime.utcnow()

    # TODO: 实际构建逻辑
    # 1. 收集规则包、评分系统、临床路径等资源
    # 2. 生成离线包文件
    # 3. 计算校验和

    # 模拟构建完成
    package.status = PackageStatus.BUILT
    package.build_completed_at = datetime.utcnow()
    package.file_size_mb = 10.5  # 示例大小
    package.checksum = "sha256:example_checksum"

    await _repo.update(package_id, package.model_dump())
    return package


async def publish_package(package_id: str) -> Optional[OfflinePackage]:
    """发布离线包。"""
    package = await get_package(package_id)
    if not package:
        return None

    if package.status != PackageStatus.BUILT:
        raise ValueError("只能发布已构建的离线包")

    package.status = PackageStatus.PUBLISHED
    package.published_at = datetime.utcnow()
    package.updated_at = datetime.utcnow()

    await _repo.update(package_id, package.model_dump())
    return package


async def get_package_stats() -> dict[str, Any]:
    """获取离线包统计。"""
    return await _repo.get_stats()
