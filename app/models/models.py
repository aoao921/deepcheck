from datetime import datetime
import uuid
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, func
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(64), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), default='user')  # admin, user
    last_login_at = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role,
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Event(db.Model):
    """安全事件表"""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.String(64), nullable=False, unique=True)
    event_name = db.Column(db.String(256))
    message = db.Column(db.Text)
    context = db.Column(db.Text)
    source = db.Column(db.String(64))
    severity = db.Column(db.String(32))
    status = db.Column(db.String(32), default='pending')
    current_round = db.Column(db.Integer, default=1)  # 当前处理轮次，默认为1
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'event_id': self.event_id,
            'event_name': self.event_name,
            'message': self.message,
            'context': self.context,
            'source': self.source,
            'severity': self.severity,
            'status': self.status,
            'current_round': self.current_round,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Task(db.Model):
    """任务表"""
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = db.Column(db.String(64), nullable=False, unique=True)
    event_id = db.Column(db.String(64))  # 关联的事件ID
    task_name = db.Column(db.String(256))
    task_type = db.Column(db.String(64))  # query, write, notify
    task_assignee = db.Column(db.String(64))
    task_status = db.Column(db.String(32), default='pending')
    round_id = db.Column(db.Integer)
    result = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'task_id': self.task_id,
            'event_id': self.event_id,
            'task_name': self.task_name,
            'task_type': self.task_type,
            'task_assignee': self.task_assignee,
            'task_status': self.task_status,
            'round_id': self.round_id,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Action(db.Model):
    """动作表"""
    __tablename__ = 'actions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    action_id = db.Column(db.String(64), nullable=False, unique=True)
    task_id = db.Column(db.String(64))  # 关联的任务ID
    round_id = db.Column(db.Integer)
    event_id = db.Column(db.String(64))  # 关联的事件ID
    action_name = db.Column(db.String(256))
    action_type = db.Column(db.String(64))
    action_assignee = db.Column(db.String(64))
    action_status = db.Column(db.String(32), default='pending')
    action_result = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'action_id': self.action_id,
            'task_id': self.task_id,
            'event_id': self.event_id,
            'round_id': self.round_id, 
            'action_name': self.action_name,
            'action_type': self.action_type,
            'action_assignee': self.action_assignee,
            'action_status': self.action_status,
            'action_result': self.action_result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Command(db.Model):
    """命令表"""
    __tablename__ = 'commands'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    command_id = db.Column(db.String(64), nullable=False, unique=True)
    action_id = db.Column(db.String(64))  # 关联的动作ID
    task_id = db.Column(db.String(64))  # 关联的任务ID
    event_id = db.Column(db.String(64))  # 关联的事件ID
    round_id = db.Column(db.Integer)
    command_name = db.Column(db.String(256))
    command_type = db.Column(db.String(64))
    command_assignee = db.Column(db.String(64))
    command_entity = db.Column(db.JSON)
    command_params = db.Column(db.JSON)
    command_status = db.Column(db.String(32), default='pending')
    command_result = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    
    def to_dict(self):
        return {
            'id': self.id,
            'command_id': self.command_id,
            'action_id': self.action_id,
            'task_id': self.task_id,
            'event_id': self.event_id,
            'round_id': self.round_id,
            'command_name': self.command_name,
            'command_type': self.command_type,
            'command_entity': self.command_entity,
            'command_params': self.command_params,
            'command_status': self.command_status,
            'command_result': self.command_result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Execution(db.Model):
    """执行表"""
    __tablename__ = 'executions'
    
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    execution_id = db.Column(db.String(48), nullable=False, unique=True)
    command_id = db.Column(db.String(48))
    action_id = db.Column(db.String(48))
    task_id = db.Column(db.String(48))
    event_id = db.Column(db.String(48))
    round_id = db.Column(db.Integer)
    execution_result = db.Column(db.Text)
    execution_summary = db.Column(db.Text)
    ai_summary = db.Column(db.Text)
    execution_status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'execution_id': self.execution_id,
            'command_id': self.command_id,
            'action_id': self.action_id,
            'task_id': self.task_id,
            'event_id': self.event_id,
            'round_id': self.round_id,
            'execution_result': self.execution_result,
            'execution_summary': self.execution_summary,
            'ai_summary': self.ai_summary,
            'execution_status': self.execution_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Message(db.Model):
    """消息表"""
    __tablename__ = 'messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(64), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    event_id = Column(String(64))  # 关联的事件ID
    message_from = Column(String(64))
    round_id = db.Column(db.Integer)
    message_content = Column(JSON)
    message_type = Column(String(32))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    def to_dict(self):
        return {
            'id': self.id,
            'message_id': self.message_id,
            'event_id': self.event_id,
            'message_from': self.message_from,
            'round_id': self.round_id,
            'message_content': self.message_content,
            'message_type': self.message_type,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Summary(db.Model):
    """事件总结表"""
    __tablename__ = 'summaries'
    
    id = db.Column(db.Integer, autoincrement=True, primary_key=True)
    summary_id = db.Column(db.String(48), nullable=False, unique=True)
    event_id = db.Column(db.String(48))
    round_id = db.Column(db.Integer, default=0)
    event_summary = db.Column(db.Text)
    event_suggestion = db.Column(db.Text)
    # root_cause = db.Column(db.Text)
    # prevention = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'summary_id': self.summary_id,
            'event_id': self.event_id,
            'round_id': self.round_id,
            'event_summary': self.event_summary,
            'event_suggestion': self.event_suggestion,
            # 'root_cause': self.root_cause,
            # 'prevention': self.prevention,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class LLMRecord(db.Model):
    """大模型请求记录表"""
    __tablename__ = "llm_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = db.Column(db.String(128), nullable=True)  # 请求ID，如OpenAI的id字段
    model_name = db.Column(db.String(64), nullable=False)  # 使用的模型名称
    created_at = db.Column(db.DateTime, default=datetime.now)  # 请求创建时间
    request_messages = db.Column(db.JSON, nullable=False)  # 请求的完整messages
    response_content = db.Column(db.Text, nullable=True)  # 响应内容
    response_full = db.Column(db.JSON, nullable=True)  # 完整响应
    prompt_tokens = db.Column(db.Integer, nullable=True)  # 提示词token数
    completion_tokens = db.Column(db.Integer, nullable=True)  # 完成词token数
    total_tokens = db.Column(db.Integer, nullable=True)  # 总token数
    cached_tokens = db.Column(db.Integer, nullable=True)  # 缓存token数
    
    def to_dict(self):
        return {
            'id': self.id,
            'request_id': self.request_id,
            'model_name': self.model_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'request_messages': self.request_messages,
            'response_content': self.response_content,
            'response_full': self.response_full,
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
            'cached_tokens': self.cached_tokens
        } 