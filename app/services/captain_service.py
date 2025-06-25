import time
import uuid
import json
from datetime import datetime
from flask import current_app
from app.models import db, Event, Task, Message, Summary
from app.services.llm_service import call_llm, parse_yaml_response
from app.controllers.socket_controller import broadcast_message
from app.services.prompt_service import PromptService
from app.utils.message_utils import create_standard_message
import yaml

import logging
logger = logging.getLogger(__name__)


def get_events_to_process():
    """获取待处理的安全事件，包括进入下一轮的事件"""
    from sqlalchemy import or_
    return Event.query.filter(
        or_(
            Event.status == 'pending',
            Event.status == 'round_finished'
        )
    ).order_by(Event.created_at.asc()).first()  

def process_event(event):
    """处理单个安全事件
    
    Args:
        event: Event对象
    """
    logger.info(f"处理事件: {event.event_id} - {event.event_name}")
    new_round = False if event.status == 'processing' else True
    round_id = event.current_round

    create_standard_message(
        event_id=event.event_id,
        message_from='system',
        round_id=round_id,
        message_type='llm_request',
        content_data="Captain on the bridge! 正在请求大模型AI指挥官。"
    )
    
    # 更新事件状态为处理中
    event.status = 'processing'
    db.session.commit()

    request_data = {
        'type': 'generate_tasks_by_event',
        'req_id': str(uuid.uuid4()),
        'res_id': str(uuid.uuid4()),
        'event_id': event.event_id,
        'round_id': round_id,
        'event_name': event.event_name if event.event_name else '{ 请大模型根据message和context生成 }',
        'message': event.message,
        'context': event.context if event.context else '无',
        'source': event.source if event.source else '无',
        'severity': event.severity if event.severity else '无',
        'created_at': event.created_at.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    tasks = []
    history_tasks = Task.query.filter_by(event_id=event.event_id).order_by(Task.created_at.desc()).all()
    for task in history_tasks:
        tasks.append({
            "task_id": task.task_id,
            "task_name": task.task_name,
            "task_type": task.task_type,
            "task_status": task.task_status,
            "task_created_at": task.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            "task_updated_at": task.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        })

    if tasks:
        request_data['history_tasks'] = tasks
    
    yaml_data = yaml.dump(request_data, allow_unicode=True, default_flow_style=False, indent=2)
    logger.info(yaml_data)

    # 针对进入下一轮的事件，提供上一轮的总结信息
    last_round_summary_content = ""
    if new_round:
        last_round_summary = Summary.query.filter_by(event_id=event.event_id).order_by(Summary.created_at.desc()).first()
        if last_round_summary:
            last_round_summary_content = f"""
                    为了方便你更加全面地分析，这里提供了你上一轮安排的任务和战况同步信息：
                    <event_progress>
                    {last_round_summary.event_summary}
                    </event_progress>
                    """
    # 构建用户提示词
    user_prompt = f"""```yaml
{yaml_data}
```
{last_round_summary_content}
针对当前网络安全事件进行分析决策，并分配适当的任务给安全管理员_manager，如果有必要。
"""
    logger.info(user_prompt)
    logger.info("--------------------------------")
    # 调用大模型
    prompt_service = PromptService('_captain')
    system_prompt = prompt_service.get_system_prompt()
    response = call_llm(system_prompt, user_prompt)
    
    logger.info(response)
    logger.info("--------------------------------")
    
    # 解析响应
    parsed_response = parse_yaml_response(response)
    if not parsed_response:
        logger.error(f"解析响应失败: {response}")
        return
    
    # 处理响应
    response_type = parsed_response.get('response_type')
    
    # 创建消息记录
    create_standard_message(
        event_id=event.event_id,
        message_from='_captain',
        round_id=parsed_response.get('round_id', round_id),
        message_type='llm_response',
        content_data=parsed_response
    )
    
    # 如果是任务分配，创建任务
    if response_type == 'TASK':
        tasks = parsed_response.get('tasks', [])
        for task_data in tasks:
            task = Task(
                task_id=str(uuid.uuid4()),
                event_id=event.event_id,
                task_name=task_data.get('task_name'),
                task_type=task_data.get('task_type'),
                task_assignee=task_data.get('task_assignee'),
                task_status='pending',
                round_id=parsed_response.get('round_id', round_id)
            )
            db.session.add(task)
        
        # 如果事件名称是默认的，使用大模型生成的名称
        event_name_from_llm = parsed_response.get('event_name', event.event_name)
        if event_name_from_llm and event_name_from_llm != event.event_name:
            event.event_name = event_name_from_llm
        db.session.commit()
    
    # 如果是任务完成，更新事件状态
    elif response_type == 'MISSION_COMPLETE':
        event.status = 'completed'
        db.session.commit()
    elif response_type == 'ROGER':
        event.status = 'error_from_llm'
        logger.error(f"调用大模型处理事件{event.event_id}失败，原因: {parsed_response.get('response_text', '未知错误')}")
        db.session.commit()

def run_captain():
    """运行Captain服务"""
    logger.info("启动Captain服务...")
    
    # 导入Flask应用
    from main import app
    
    # 使用应用上下文
    with app.app_context():
        while True:
            try:
                # 获取待处理事件
                event = get_events_to_process()
                if event:
                    process_event(event)
                else:
                    logger.info("没有待处理事件，等待中...")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"处理事件时出错: {e}")
                time.sleep(5)