import time
import uuid
import json
import threading
from datetime import datetime
from flask import current_app
from sqlalchemy import func, and_, or_
from app.models import db, Event, Task, Action, Command, Execution, Summary, Message
from app.services.llm_service import call_llm, parse_yaml_response
from app.controllers.socket_controller import broadcast_message
from app.services.prompt_service import PromptService
from app.config import config
from app.utils.message_utils import create_standard_message
import logging
import yaml

logger = logging.getLogger(__name__)

def get_executions_for_summarization():
    """获取需要生成摘要的执行结果
    
    Returns:
        需要生成摘要的执行结果列表
    """
    # 查询所有completed状态的执行
    # 在新的状态流转逻辑中，completed状态表示执行已完成但尚未生成摘要
    # 生成摘要后状态会更新为summarized
    completed_executions = Execution.query.filter(
        Execution.execution_status.in_(['completed'])
    ).order_by(Execution.created_at.asc()).all()
    
    logger.info(f"找到 {len(completed_executions)} 个completed状态的执行结果需要生成摘要")
    
    return completed_executions

def process_execution_summary(execution):
    """处理单个执行结果，生成摘要
    
    Args:
        execution: 执行对象
    """
    logger.info(f"处理执行结果摘要: {execution.execution_id}")
    
    try:
        # 获取执行结果
        execution_result = execution.execution_result
        if not execution_result:
            logger.warning(f"执行结果为空: {execution.execution_id}")
            return
        
        # 如果执行结果是字符串（JSON字符串），则解析为对象
        if isinstance(execution_result, str):
            try:
                execution_result = json.loads(execution_result)
            except json.JSONDecodeError:
                # 如果不是有效的JSON，则保持原样
                pass
        
        # 获取关联的命令、动作和任务信息
        command = Command.query.filter_by(command_id=execution.command_id).first()
        action = Action.query.filter_by(action_id=execution.action_id).first() if execution.action_id else None
        task = Task.query.filter_by(task_id=execution.task_id).first() if execution.task_id else None
        
        # 构建上下文信息
        context = {
            "execution_id": execution.execution_id,
            "command_id": execution.command_id,
            "command_name": command.command_name if command else "未知命令",
            "command_type": command.command_type if command else "未知类型",
            "action_id": execution.action_id,
            "action_name": action.action_name if action else "未知动作",
            "task_id": execution.task_id,
            "task_name": task.task_name if task else "未知任务",
            "event_id": execution.event_id,
            "round_id": execution.round_id,
            "execution_status": execution.execution_status,
            "execution_result": execution_result,
            "req_id": str(uuid.uuid4()),
            "res_id": str(uuid.uuid4())
        }
        
        # 将上下文转换为JSON格式
        json_context = json.dumps(context, indent=2, ensure_ascii=False)

        # 构建系统提示词
        system_prompt = """
        你是一个经验丰富的安全专家，擅长从执行结果中提取关键信息，并用精炼的文字生成适合人类阅读的文本。
        请不要做总结评论，只保留客观结果。
        """
        
        # 构建用户提示词
        user_prompt = f"""
            ```json
            {json_context}
            ```
            以上是基于_caption的任务安排，和_manager的动作细化，以及_operator的命令设置，通过SOAR安全之剧本执行的返回结果。
            当然也有可能是，人类工程师在页面手工完成的处置结果。
            请从信息提炼的角度，帮我提取关键信息，作客观结果的保留，不需要做总结评论。
            简单地说，就是告诉我剧本做了什么，得到了什么结果，不窜改，不臆造。
            """
        
        # 调用大模型生成摘要
        prompt_service = PromptService('_expert')
        # 使用自定义系统提示词
        # system_prompt = prompt_service.get_system_prompt()

        logger.info(f"生成摘要: {execution.execution_id}")
        create_standard_message(
            event_id=execution.event_id,
            message_from='system',
            round_id=execution.round_id,
            message_type='llm_request',
            content_data="正在请求大模型，生成执行结果摘要，请耐心等待......"
        )
        
        # 使用长文本模型
        response = call_llm(system_prompt, user_prompt)
        
        logger.info(f"生成摘要成功: {execution.execution_id}\n{response}")
        
        # 更新执行结果的摘要字段
        execution.ai_summary = response
        
        # 更新执行结果状态为已总结
        execution.execution_status = 'summarized'
        
        db.session.commit()
        
        # 创建消息记录
        create_execution_summary_message(execution, response)
        
    except Exception as e:
        print(11)
        error_msg = f"处理执行结果摘要时出错: {str(e)}"
        logger.error(error_msg)

def get_commands_with_completed_executions():
    """获取所有执行已完成但命令状态未更新的命令
    
    Returns:
        命令列表
    """
    # 查询所有processing状态的命令
    processing_commands = Command.query.filter_by(command_status='processing').all()
    
    # 过滤出所有执行已完成的命令
    result = []
    for command in processing_commands:
        if check_command_completion(command.command_id):
            result.append(command)
    
    return result

def check_command_completion(command_id):
    """检查命令下的所有执行是否已完成
    
    Args:
        command_id: 命令ID
    
    Returns:
        是否所有执行都已完成
    """
    # 获取命令下的所有执行
    executions = Execution.query.filter_by(command_id=command_id).all()
    
    # 如果没有执行记录，返回False
    if not executions:
        return False
    
    # 检查是否所有执行都已完成
    for execution in executions:
        if execution.execution_status not in ['summarized', 'failed']:
            return False
    
    return True

def update_command_status(command_id):
    """更新命令状态
    
    Args:
        command_id: 命令ID
    """
    # 获取命令
    command = Command.query.filter_by(command_id=command_id).first()
    if not command:
        logger.warning(f"命令不存在: {command_id}")
        return
    
    # 获取命令下的所有执行
    executions = Execution.query.filter_by(command_id=command_id).all()
    
    # 如果没有执行记录，返回
    if not executions:
        logger.warning(f"命令没有执行记录: {command_id}")
        return
    
    # 检查执行状态
    has_failed = any(execution.execution_status == 'failed' for execution in executions)
    all_summarized = all(execution.execution_status == 'summarized' or execution.execution_status == 'failed' for execution in executions)
    has_pending_or_processing = any(execution.execution_status in ['pending', 'processing', 'completed'] for execution in executions)
    
    # 更新命令状态
    if has_failed and all_summarized:
        # 如果有失败的执行，且所有执行都已经总结或失败，则标记为失败
        command.command_status = 'failed'
    elif all_summarized:
        # 如果所有执行都已经总结或失败，且没有失败的执行，则标记为完成
        command.command_status = 'completed'
    elif has_pending_or_processing:
        # 如果有执行仍在处理中，则保持处理中状态
        command.command_status = 'processing'
    
    db.session.commit()
    logger.info(f"更新命令状态: {command_id} -> {command.command_status}")
    
    # 只有当命令状态为completed或failed时，才检查是否需要更新任务状态
    if command.command_status in ['completed', 'failed']:
        check_task_completion(command.task_id)

def get_tasks_with_completed_commands():
    """获取所有命令已完成但任务状态未更新的任务
    
    Returns:
        任务列表
    """
    # 查询所有processing状态的任务
    processing_tasks = Task.query.filter_by(task_status='processing').all()
    
    # 过滤出所有命令已完成的任务
    result = []
    for task in processing_tasks:
        if check_task_completion(task.task_id):
            result.append(task)
    
    return result

def check_task_completion(task_id):
    """检查任务下的所有命令是否已完成
    
    Args:
        task_id: 任务ID
    
    Returns:
        是否所有命令都已完成
    """
    # 获取任务下的所有命令
    commands = Command.query.filter_by(task_id=task_id).all()
    
    # 如果没有命令记录，返回False
    if not commands:
        return False
    
    # 检查是否所有命令都已完成
    for command in commands:
        if command.command_status not in ['completed', 'failed']:
            return False
    
    # 更新任务状态
    update_task_status(task_id)
    
    return True

def update_task_status(task_id):
    """更新任务状态
    
    Args:
        task_id: 任务ID
    """
    # 获取任务
    task = Task.query.filter_by(task_id=task_id).first()
    if not task:
        logger.warning(f"任务不存在: {task_id}")
        return
    
    # 获取任务下的所有命令
    commands = Command.query.filter_by(task_id=task_id).all()
    
    # 检查是否有失败的命令
    has_failed = any(command.command_status == 'failed' for command in commands)
    
    # 更新任务状态
    if has_failed:
        task.task_status = 'failed'
    else:
        task.task_status = 'completed'
    
    db.session.commit()
    logger.info(f"更新任务状态: {task_id} -> {task.task_status}")
    
    # 检查是否需要更新事件轮次状态
    check_event_round_completion(task.event_id, task.round_id)

def get_event_rounds_with_completed_tasks():
    """获取所有任务已完成但事件轮次状态未更新的事件轮次
    
    Returns:
        (event_id, round_id)元组列表
    """
    # 查询所有处理中状态的事件
    events = Event.query.filter_by(status='processing').all()
    
    # 获取所有事件的当前轮次任务完成情况
    result = []
    for event in events:
        # 获取事件的当前轮次
        current_round = event.current_round or 1
        
        # 检查该轮次的所有任务是否已完成
        tasks = Task.query.filter_by(event_id=event.event_id, round_id=current_round).all()
        
        # 如果没有任务，跳过
        if not tasks:
            continue
        
        # 检查是否所有任务都已完成
        all_completed = True
        for task in tasks:
            if task.task_status not in ['completed', 'failed']:
                all_completed = False
                break
        
        # 如果所有任务都已完成，添加到结果列表
        if all_completed:
            result.append((event.event_id, current_round))
    
    return result

def check_event_round_completion(event_id, round_id):
    """检查事件轮次下的所有任务是否已完成
    
    Args:
        event_id: 事件ID
        round_id: 轮次ID
    
    Returns:
        是否所有任务都已完成
    """
    # 获取事件轮次下的所有任务
    tasks = Task.query.filter_by(event_id=event_id, round_id=round_id).all()
    
    # 如果没有任务记录，返回False
    if not tasks:
        return False
    
    # 检查是否所有任务都已完成
    for task in tasks:
        if task.task_status not in ['completed', 'failed']:
            return False
    
    # 检查所有执行结果是否都已完成或失败
    executions = Execution.query.filter_by(event_id=event_id, round_id=round_id).all()
    
    # 如果有执行记录，检查它们的状态
    if executions:
        for execution in executions:
            # 如果有任何执行结果处于waiting或processing状态，则认为轮次未完成
            if execution.execution_status in ['waiting', 'processing', 'completed']:
                logger.info(f"事件 {event_id} 轮次 {round_id} 有执行结果处于 {execution.execution_status} 状态，轮次未完成")
                return False
    
    # 更新事件轮次状态
    update_event_round_status(event_id, round_id)
    
    return True

def update_event_round_status(event_id, round_id):
    """更新事件轮次状态
    
    Args:
        event_id: 事件ID
        round_id: 轮次ID
    """
    # 获取事件
    event = Event.query.filter_by(event_id=event_id).first()
    if not event:
        logger.warning(f"事件不存在: {event_id}")
        return
    
    # 获取事件轮次下的所有任务
    tasks = Task.query.filter_by(event_id=event_id, round_id=round_id).all()
    
    # 检查是否有失败的任务
    has_failed = any(task.task_status == 'failed' for task in tasks)
    
    # 检查所有执行结果是否都已完成或失败
    executions = Execution.query.filter_by(event_id=event_id, round_id=round_id).all()
    
    # 如果有执行结果处于waiting或processing状态，则不更新事件状态
    if executions and any(execution.execution_status in ['waiting', 'processing', 'completed'] for execution in executions):
        logger.info(f"事件 {event_id} 轮次 {round_id} 有执行结果未完成，不更新事件状态")
        return
    
    # 更新事件状态
    if has_failed:
        event.status = 'failed'
    else:
        # 更新事件的当前轮次
        event.current_round = round_id
        
        # 当前轮次的任务已完成，将状态设置为round_finished
        event.status = 'round_finished'
        
        # 生成事件总结
        db.session.commit()
        logger.info(f"更新事件轮次状态: {event_id}, 轮次: {round_id} -> {event.status}, 当前轮次: {event.current_round}")
        generate_event_summary(event_id)
        
        # 如果已经达到最大轮次，则标记为已完成
        if round_id >= config.EVENT_MAX_ROUND:
            event.status = 'completed'
            db.session.commit()
            logger.info(f"事件已达到最大轮次，标记为已完成: {event_id}, 最终状态: {event.status}")
            return
    
    db.session.commit()
    logger.info(f"更新事件轮次状态: {event_id}, 轮次: {round_id} -> {event.status}, 当前轮次: {event.current_round}")

def get_events_for_summary():
    """获取需要生成总结的事件
    
    Returns:
        事件列表
    """
    # 只查询round_finished状态的事件，不包括completed状态
    events = Event.query.filter_by(status='round_finished').all()
    
    return events

def generate_event_summary(event_id):
    """生成事件总结
    
    Args:
        event_id: 事件ID
    """
    # 获取事件
    event = Event.query.filter_by(event_id=event_id).first()
    if not event:
        logger.warning(f"事件不存在: {event_id}")
        return
    
    # 只有round_finished和completed状态的事件才生成总结。
    # 因为round_finished状态的事件，表示当前轮次的事件已经处理完成。
    # completed状态的事件，表示所有轮次的事件已经处理完成。
    if event.status not in ['round_finished', 'completed']:
        logger.info(f"事件状态不是round_finished/completed，不生成总结: {event_id}, 当前状态: {event.status}")
        return
    
    try:
        logger.info(f"生成事件总结: {event_id}, 当前轮次: {event.current_round}, 状态: {event.status}")
        
        # 获取事件相关信息
        tasks = Task.query.filter_by(event_id=event_id).all()
        actions = Action.query.filter_by(event_id=event_id).all()
        commands = Command.query.filter_by(event_id=event_id).all()
        executions = Execution.query.filter_by(event_id=event_id).all()

        tasks_data = []
        for task in tasks:
            tasks_data.append({
                "task_id": task.task_id,
                "task_name": task.task_name,
                "task_status": task.task_status
            })
        
        actions_data = []
        for action in actions:
            actions_data.append({
                "action_id": action.action_id,
                "action_name": action.action_name,
                "action_status": action.action_status
            })

        commands_data = []
        for command in commands:
            commands_data.append({
                "command_id": command.command_id,
                "command_name": command.command_name,
                "command_status": command.command_status
            })

        executions_data = []
        for execution in executions:
            executions_data.append({
                "execution_id": execution.execution_id,
                "execution_status": execution.execution_status,
                "command_id": execution.command_id,
                "round_id": execution.round_id,
                "ai_summary": execution.ai_summary
            })
        
        # 获取上一次的总结（如果有）
        previous_summary = Summary.query.filter_by(event_id=event_id).order_by(Summary.created_at.desc()).first()
        
        # 构建上下文信息
        context = {
            "from": "system",
            "to": "_expert",
            "type": "generate_event_summary",
            "event_id": event_id,
            "event_name": event.event_name,
            "event_message": event.message,
            "round_id": event.current_round,
            "event_status": event.status,
            "tasks_data": tasks_data,
            "actions_data": actions_data,
            "commands_data": commands_data,
            "executions_data": executions_data,
            "req_id": str(uuid.uuid4()),
            "res_id": str(uuid.uuid4())
        }
        
        # 如果有上一次总结，添加到上下文
        if previous_summary:
            context["previous_summary"] = previous_summary.event_summary
        
        # 将上下文转换为JSON格式
        json_context = json.dumps(context, indent=2, ensure_ascii=False)
        
        # 构建系统提示词
        system_prompt = """
        你是一个经验丰富的安全专家，擅长分析安全事件并提供专业的总结和建议。
        请根据提供的安全事件信息，生成一份全面的事件总结报告，包括事件概述、根本原因分析、处置建议和预防措施。
        """
        
        # 构建用户提示词
        user_prompt = f"""
                    ```json
                    {json_context}
                    ```

                    请根据以上安全事件信息，生成一份战况汇报，方便_captain基于此再次决策，包括以下几个部分：

                    1. 回顾_captain安排的任务
                    2. 总结任务最终完成的情况
                    3. 不要做总结和分析，只需要客观事实，不要窜改，不要臆造。
                    4. 你不负责分析，这些工作由_captain完成。
                    """
        
        # 如果有上一次总结，添加相关提示
        if previous_summary:
            user_prompt += """
                请注意，我已经提供了上一次的事件总结。请基于这个总结进行更新和完善，确保新的总结能够：
                1. 保留上一次总结中的重要信息
                2. 添加新发现的信息和见解
                3. 如有必要，修正或更新上一次总结中的内容
                4. 使整体总结更加全面和连贯
                """
        
        # 如果事件已解决，添加相关提示
        if event.status == 'resolved':
            user_prompt += """
            您的输出格式有要求，必须为JSON格式，如下：
            ```json
            {
                "from": "_expert",
                "type": "llm_response",
                "response_type": "event_summary",
                "event_id": "事件ID，请求携带",
                "event_name": "事件名称，请求携带",
                "round_id": "事件轮次，请求携带",
                "summary": "事件总结",
                "req_id": "来自用户请求",
                "res_id": "来自用户请求",
            }
            ```
            请注意，此事件已被人工标记为已解决。请在总结中反映这一点。
            """
        
        create_standard_message(
            event_id=event_id,
            message_from='system',
            round_id=event.current_round,
            message_type='llm_request',
            content_data="正在请求大模型，生成事件总结，请耐心等待......"
        )
        # 调用大模型生成总结
        response = call_llm(system_prompt, user_prompt, temperature=0.3)
        
        logger.info(f"生成事件总结成功: {event_id}")

        # 尝试解析响应
        summary_text = ""
        try:
            # 首先尝试解析为JSON
            # 仅替换一次json标记和结尾的```标记
            fixed_response = response.replace("```json", "", 1).rstrip().rstrip("```").strip()
            response_data = json.loads(fixed_response)
            summary_text = response_data.get("summary", "")
            
            # 检查事件ID是否匹配
            if not event.event_id == response_data.get("event_id", ""):
                logger.warning(f"事件ID不匹配: {event.event_id} != {response_data.get('event_id', '')}")
                return
        except Exception as e:
            logger.warning(f"解析事件总结时出错: {str(e)} ，使用原始响应作为总结")
            summary_text = response  # 使用原始响应作为总结
        
        # 创建总结记录
        summary = Summary(
            summary_id=str(uuid.uuid4()),
            event_id=event_id,
            round_id=event.current_round,  # 使用事件的当前轮次
            event_summary=summary_text.strip() if summary_text else "",
            event_suggestion=""
        )
        db.session.add(summary)
        db.session.commit()
        logger.info(f"事件总结已保存: {event_id}")
        
        # 创建消息记录
        create_event_summary_message(event, summary)
        
    except Exception as e:
        error_msg = f"生成事件总结时出错: {str(e)}"
        logger.error(error_msg)

def create_execution_summary_message(execution, summary):
    """创建执行结果摘要消息
    
    Args:
        execution: 执行对象
        summary: 摘要内容
    """
    # 构造消息内容
    content_data = {
        "execution_id": execution.execution_id,
        "command_id": execution.command_id,
        "action_id": execution.action_id,
        "task_id": execution.task_id,
        "ai_summary": execution.ai_summary
    }
    
    # 创建标准消息
    create_standard_message(
        event_id=execution.event_id,
        message_from='_expert',
        round_id=execution.round_id,
        message_type='execution_summary',
        content_data=content_data
    )

def create_event_summary_message(event, summary):
    """创建事件总结消息
    
    Args:
        event: 事件对象
        summary: 总结对象
    """
    # 构造消息内容
    content_data = {
        "event_id": event.event_id,
        "event_name": event.event_name,
        "event_status": event.status,
        "round_id": event.current_round,
        "event_summary": summary.event_summary,
        "event_suggestion": summary.event_suggestion
    }
    
    # 创建标准消息
    create_standard_message(
        event_id=event.event_id,
        message_from='_expert',
        round_id=event.current_round,
        message_type='event_summary',
        content_data=content_data
    )

# 线程函数：处理执行结果摘要
def execution_summary_worker(app):
    """处理执行结果摘要的工作线程"""
    with app.app_context():
        logger.info("启动执行结果摘要处理线程")
        while True:
            try:
                # 获取待处理的执行结果
                pending_executions = get_executions_for_summarization()
                
                if pending_executions:
                    logger.info(f"发现 {len(pending_executions)} 个待处理的执行结果")
                    
                    # 处理每个执行结果
                    for execution in pending_executions:
                        process_execution_summary(execution)
                else:
                    logger.debug("没有待处理的执行结果，等待中...")
                    time.sleep(5)
            except Exception as e:
                logger.error(f"处理执行结果摘要时出错: {str(e)}")
                time.sleep(5)

# 线程函数：处理命令状态更新
def command_status_worker(app):
    """处理命令状态更新的工作线程"""
    with app.app_context():
        logger.info("启动命令状态更新线程")
        while True:
            try:
                # 获取待处理的命令
                pending_commands = get_commands_with_completed_executions()
                
                if pending_commands:
                    logger.info(f"发现 {len(pending_commands)} 个待更新状态的命令")
                    
                    # 处理每个命令
                    for command in pending_commands:
                        update_command_status(command.command_id)
                else:
                    logger.debug("没有待更新状态的命令，等待中...")
                    time.sleep(10)
            except Exception as e:
                logger.error(f"处理命令状态更新时出错: {str(e)}")
                time.sleep(10)

# 线程函数：处理任务状态更新
def task_status_worker(app):
    """处理任务状态更新的工作线程"""
    with app.app_context():
        logger.info("启动任务状态更新线程")
        while True:
            try:
                # 获取待处理的任务
                pending_tasks = get_tasks_with_completed_commands()
                
                if pending_tasks:
                    logger.info(f"发现 {len(pending_tasks)} 个待更新状态的任务")
                    
                    # 处理每个任务
                    for task in pending_tasks:
                        check_task_completion(task.task_id)
                else:
                    logger.debug("没有待更新状态的任务，等待中...")
                    time.sleep(15)
            except Exception as e:
                logger.error(f"处理任务状态更新时出错: {str(e)}")
                time.sleep(15)

# 线程函数：处理事件轮次状态更新
def event_round_status_worker(app):
    """处理事件轮次状态更新的工作线程"""
    with app.app_context():
        logger.info("启动事件轮次状态更新线程")
        while True:
            try:
                # 获取待处理的事件轮次
                pending_rounds = get_event_rounds_with_completed_tasks()
                
                if pending_rounds:
                    logger.info(f"发现 {len(pending_rounds)} 个待更新状态的事件轮次")
                    
                    # 处理每个事件轮次
                    for event_id, round_id in pending_rounds:
                        if not check_event_round_completion(event_id, round_id):
                            time.sleep(10)
                else:
                    logger.debug("没有待更新状态的事件轮次，等待中...")
                    time.sleep(20)
            except Exception as e:
                logger.error(f"处理事件轮次状态更新时出错: {str(e)}")
                time.sleep(20)

# 线程函数：处理事件总结生成
def event_summary_worker(app):
    """处理事件总结生成的工作线程"""
    with app.app_context():
        logger.info("启动事件总结生成线程")
        while True:
            try:
                # 获取待处理的事件
                pending_events = get_events_for_summary()
                
                if pending_events:
                    logger.info(f"发现 {len(pending_events)} 个待生成总结的事件")
                    
                    # 处理每个事件
                    for event in pending_events:
                        generate_event_summary(event.event_id)
                        
                        # 如果事件状态为round_finished，且未达到最大轮次，可以自动推进到下一轮
                        # 注意：这里可以根据实际需求决定是否自动推进，或者由外部触发
                        if event.status == 'round_finished' and event.current_round <= config.EVENT_MAX_ROUND:
                            advance_event_to_next_round(event.event_id)
                else:
                    logger.debug("没有待生成总结的事件，等待中...")
                    time.sleep(30)
            except Exception as e:
                logger.error(f"处理事件总结生成时出错: {str(e)}")
                time.sleep(30)

def run_expert():
    """运行_expert服务"""
    logger.info("启动_expert服务...")
    
    # 导入Flask应用
    from main import app
    
    # 创建并启动工作线程
    threads = []
    
    # 线程1：处理执行结果摘要
    t1 = threading.Thread(target=execution_summary_worker, args=(app,))
    t1.daemon = True
    threads.append(t1)
    
    # 线程2：处理命令状态更新
    t2 = threading.Thread(target=command_status_worker, args=(app,))
    t2.daemon = True
    threads.append(t2)
    
    # 线程3：处理任务状态更新
    t3 = threading.Thread(target=task_status_worker, args=(app,))
    t3.daemon = True
    threads.append(t3)
    
    # 线程4：处理事件轮次状态更新
    t4 = threading.Thread(target=event_round_status_worker, args=(app,))
    t4.daemon = True
    threads.append(t4)
    
    # 线程5：处理事件总结生成
    t5 = threading.Thread(target=event_summary_worker, args=(app,))
    t5.daemon = True
    threads.append(t5)
    
    # 启动所有线程
    for t in threads:
        t.start()
    
    # 等待所有线程结束（实际上不会结束，除非程序被终止）
    for t in threads:
        t.join()

def advance_event_to_next_round(event_id):
    """将事件推进到下一轮处理
    
    Args:
        event_id: 事件ID
    
    Returns:
        bool: 是否成功推进到下一轮
    """
    # 获取事件
    event = Event.query.filter_by(event_id=event_id).first()
    if not event:
        logger.warning(f"事件不存在: {event_id}")
        return False
    
    # 只有round_finished状态的事件才能推进到下一轮
    if event.status != 'round_finished':
        logger.warning(f"事件状态不是round_finished，无法推进到下一轮: {event_id}, 当前状态: {event.status}")
        return False
    
    # 获取当前轮次
    current_round = event.current_round or 1
    
    # 检查是否已达到最大轮次
    if current_round >= config.EVENT_MAX_ROUND:
        logger.warning(f"事件已达到最大轮次，无法推进到下一轮: {event_id}, 当前轮次: {current_round}")
        return False
    
    # 更新轮次和状态
    event.current_round = current_round + 1
    event.status = 'pending'  # 设置为待处置状态
    
    db.session.commit()
    logger.info(f"事件推进到下一轮: {event_id}, 新轮次: {event.current_round}")
    
    return True

def resolve_event(event_id, resolution_note=None):
    """人工解决事件
    
    Args:
        event_id: 事件ID
        resolution_note: 解决说明
    
    Returns:
        bool: 是否成功解决事件
    """
    # 获取事件
    event = Event.query.filter_by(event_id=event_id).first()
    if not event:
        logger.warning(f"事件不存在: {event_id}")
        return False
    
    # 更新事件状态为已解决
    event.status = 'resolved'
    
    # 如果有解决说明，可以保存到事件的上下文中
    if resolution_note:
        # 尝试解析现有上下文
        try:
            context = json.loads(event.context) if event.context else {}
        except:
            context = {}
        
        # 添加解决说明
        context['resolution_note'] = resolution_note
        event.context = json.dumps(context)
    
    db.session.commit()
    logger.info(f"事件已人工解决: {event_id}")
    
    # 生成最终的事件总结
    generate_event_summary(event_id)
    
    return True 