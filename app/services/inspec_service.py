import logging
import json
from typing import Dict, Any, Optional
from app.config import config
from app.models import db, Command, Execution
import uuid

# 导入SOARClient
from app.utils.inspec_client import InspecClient

logger = logging.getLogger(__name__)

def decode_bytes(obj):
    """递归地将对象中的 bytes 解码为 str"""
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    elif isinstance(obj, dict):
        return {key: decode_bytes(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [decode_bytes(item) for item in obj]
    else:
        return obj

# 使用示例
complex_data = {
    "name": b"Alice",
    "tags": [b"python", b"json"],
    "metadata": {
        "source": b"file.txt"
    }
}

# 先解码所有 bytes
clean_data = decode_bytes(complex_data)
# 再进行 JSON 序列化
json_string = json.dumps(clean_data)
class InspecService:
    def __init__(self):
        self.inspec_client = InspecClient()

    def execute_script(self, command: Command) -> Dict[str, Any]:
        """
        执行SOAR剧本

        Args:
            command: 命令对象

        Returns:
            执行结果
        """
        try:
            # 获取剧本ID和参数
            script_id = command.command_entity.get('script_id')
            params = command.command_params or {}

            if not script_id:
                error_msg = "缺少脚本ID"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "message": error_msg
                }

            # 执行剧本
            logger.info(f"执行脚本: {script_id}, 参数: {params}")
            # activity_id = self.soar_client.execute_playbook(playbook_id, params)
            result = self.inspec_client.execute_profile(script_id,params)

            if not result:
                error_msg = "脚本执行失败，未获取到执行结果"
                logger.error(error_msg)
                return {
                    "status": "failed",
                    "message": error_msg
                }
            # if not result:
            #     error_msg = f"剧本执行超时或失败: {activity_id}"
            #     logger.error(error_msg)
            #     return {
            #         "status": "failed",
            #         "message": error_msg
            #     }

            # 记录执行结果
            # del result['result']
            del result['stdout']
            del result['output']
            del result['stderr']
            print(result)
            # result=json.loads(result)

            # 直接截取前 30 个，自动处理不足 30 的情况
            result['result']['profiles'][0]['controls'] = result['result']['profiles'][0]['controls'][:30]

            execution = Execution(
                execution_id=str(uuid.uuid4()),
                command_id=command.command_id,
                action_id=command.action_id,
                task_id=command.task_id,
                event_id=command.event_id,
                round_id=command.round_id,
                execution_result=json.dumps(result),
                execution_summary=f"脚本 {script_id} 执行成功",
                execution_status="completed"
            )
            db.session.add(execution)
            db.session.commit()

            logger.info(f"脚本 {script_id} 执行成功，结果: {result}")

            return {
                "status": "success",
                "message": f"脚本 {script_id} 执行成功",
                "data": result
            }

        except Exception as e:
            error_msg = f"执行脚本时出错: {str(e)}"
            logger.error(error_msg)

            # 记录执行失败
            execution = Execution(
                execution_id=str(uuid.uuid4()),
                command_id=command.command_id,
                action_id=command.action_id,
                task_id=command.task_id,
                event_id=command.event_id,
                round_id=command.round_id,
                execution_result=json.dumps({"error": str(e)}),
                execution_summary=error_msg,
                execution_status="failed"
            )
            db.session.add(execution)
            db.session.commit()

            return {
                "status": "failed",
                "message": error_msg
            }