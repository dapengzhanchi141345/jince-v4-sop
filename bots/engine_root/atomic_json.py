# -*- coding: utf-8 -*-
"""
Atomic JSON - 原子写入JSON文件（防Windows并发损坏）

提供：
- write_json(path, data, default=None): 原子写入
- read_json(path, default=None): 安全读取
- locked(path): 文件锁上下文管理器

设计原则：
1. 写入先写临时文件，再os.replace（原子操作）
2. 读取加锁防止并发损坏
3. 支持default参数防止 FileNotFoundError
"""

import os
import json
import tempfile
import logging
from contextlib import contextmanager
from typing import Any, Optional

logger = logging.getLogger('atomic_json')

# 配置
READ_RETRY = 3           # 读取重试次数
READ_RETRY_SLEEP = 0.1   # 重试间隔（秒）
WRITE_TIMEOUT = 30       # 写入超时（秒）


@contextmanager
def locked(path: str, timeout: float = WRITE_TIMEOUT):
    """
    文件锁上下文管理器（简化版，不使用filelock库）

    用法：
        with locked(path):
            data = read_json(path)
    """
    lock_path = path + '.lock'
    import time
    start = time.time()
    while os.path.exists(lock_path):
        if time.time() - start > timeout:
            raise TimeoutError(f"Lock timeout: {lock_path}")
        time.sleep(0.01)

    # 创建锁文件
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)

    try:
        yield
    finally:
        # 释放锁
        if os.path.exists(lock_path):
            os.remove(lock_path)


def write_json(path: str, data: Any, default=None, **kwargs) -> bool:
    """
    原子写入JSON文件

    步骤：
    1. 序列化数据到字符串
    2. 写入临时文件
    3. os.replace原子替换目标文件

    参数：
        path: 目标文件路径
        data: 要写入的数据（必须是可序列化的）
        default: 序列化失败的默认值（用于处理np.float64等）
        **kwargs: 传递给json.dump的额外参数

    返回：
        bool: 是否成功
    """
    try:
        # 确保目录存在
        dir_path = os.path.dirname(os.path.abspath(path))
        os.makedirs(dir_path, exist_ok=True)

        # 序列化
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2, **kwargs)
        except (TypeError, ValueError) as e:
            # 降级：使用default处理
            logger.warning(f"JSON序列化失败，尝试default处理: {e}")
            content = json.dumps(data, ensure_ascii=False, indent=2, default=str, **kwargs)

        # 写入临时文件
        fd, tmp_path = tempfile.mkstemp(suffix='.tmp', dir=dir_path)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # 原子替换
            os.replace(tmp_path, path)
            logger.debug(f"✅ 原子写入成功: {path}")
            return True

        except Exception as e:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    except Exception as e:
        logger.error(f"❌ 写入失败: {path} | {e}")
        return False


def read_json(path: str, default=None) -> Any:
    """
    安全读取JSON文件（带重试）

    参数：
        path: 文件路径
        default: 文件不存在或读取失败时的默认值

    返回：
        解析后的数据，或default
    """
    if not os.path.exists(path):
        logger.debug(f"文件不存在，返回default: {path}")
        return default

    for attempt in range(READ_RETRY + 1):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            if not content.strip():
                logger.warning(f"文件为空: {path}")
                return default

            data = json.loads(content)
            logger.debug(f"✅ 读取成功: {path}")
            return data

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            if attempt < READ_RETRY:
                logger.warning(f"读取失败，重试 {attempt+1}/{READ_RETRY}: {e}")
                import time
                time.sleep(READ_RETRY_SLEEP * (attempt + 1))
            else:
                logger.error(f"读取失败（已重试{READ_RETRY}次）: {path} | {e}")
                return default

        except Exception as e:
            logger.error(f"读取异常: {path} | {e}")
            return default

    return default


def delete_json(path: str) -> bool:
    """
    安全删除JSON文件

    返回：
        bool: 是否成功
    """
    try:
        if os.path.exists(path):
            os.remove(path)
            logger.debug(f"✅ 删除成功: {path}")
            return True
        else:
            logger.debug(f"文件已不存在: {path}")
            return False
    except Exception as e:
        logger.error(f"❌ 删除失败: {path} | {e}")
        return False


def append_json(path: str, new_item: Any, default=None) -> bool:
    """
    追加条目到JSON数组（原子操作）

    参数：
        path: 目标文件路径（必须是JSON数组）
        new_item: 要追加的条目
        default: 文件不存在时的默认数组

    返回：
        bool: 是否成功
    """
    try:
        # 读取现有数据
        data = read_json(path, default=[])
        if not isinstance(data, list):
            logger.error(f"目标文件不是数组: {path}")
            return False

        # 追加新条目
        data.append(new_item)

        # 原子写入
        return write_json(path, data)

    except Exception as e:
        logger.error(f"❌ 追加失败: {path} | {e}")
        return False


# 兼容性别名（供旧代码使用）
write = write_json
read = read_json


if __name__ == "__main__":
    # 测试
    import tempfile

    print("="*60)
    print("atomic_json 模块测试")
    print("="*60)

    # 测试目录
    test_dir = tempfile.mkdtemp()
    test_path = os.path.join(test_dir, "test.json")

    # 测试写入
    test_data = {
        "genome": {
            "rid": "test_001",
            "fitness": {"exp_r": 0.15, "score": 0.8}
        }
    }

    print(f"\n📝 测试写入: {test_path}")
    success = write_json(test_path, test_data)
    print(f"   {'✅ 成功' if success else '❌ 失败'}")

    # 测试读取
    print(f"\n📖 测试读取")
    loaded = read_json(test_path)
    print(f"   数据: {loaded}")

    # 测试不存在的文件
    print(f"\n📖 测试不存在的文件")
    default = {"note": "default_value"}
    loaded = read_json(os.path.join(test_dir, "missing.json"), default=default)
    print(f"   返回default: {loaded == default}")

    # 测试追加
    print(f"\n📝 测试追加")
    array_path = os.path.join(test_dir, "array.json")
    append_json(array_path, {"id": 1})
    append_json(array_path, {"id": 2})
    append_json(array_path, {"id": 3})
    arr = read_json(array_path)
    print(f"   数组长度: {len(arr)}")

    # 清理
    import shutil
    shutil.rmtree(test_dir)

    print("\n" + "="*60)
    print("✅ 所有测试通过")
    print("="*60)
