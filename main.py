import os
import sys
import argparse
import logging
from flask import Flask, jsonify, render_template, redirect, url_for, request, make_response
from flask_socketio import SocketIO
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity, verify_jwt_in_request, get_jwt, decode_token
from functools import wraps
from dotenv import load_dotenv
from app.models import db
from app.utils.logging_config import configure_logging
from app.models.models import User
from app.controllers.heimdallite_controller import heimdallite_bp
# 配置日志
logger = configure_logging()

# 加载环境变量
load_dotenv()

# 创建Flask应用
app = Flask(__name__, 
            static_folder='app/static',
            template_folder='app/templates')
app.register_blueprint(heimdallite_bp)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'deepsoc_secret_key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///deepsoc.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# JWT配置
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'deepsoc_jwt_secret_key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 86400))
app.config['JWT_TOKEN_LOCATION'] = ['headers', 'cookies']  # 从头部和Cookie中获取令牌
app.config['JWT_COOKIE_CSRF_PROTECT'] = False  # 简化起见，禁用CSRF保护

# 初始化JWT
jwt = JWTManager(app)

# 初始化数据库
db.init_app(app)

# 初始化迁移
migrate = Migrate(app, db)

# 初始化SocketIO，添加更多配置选项
socketio = SocketIO(
    app, 
    cors_allowed_origins="*",
    async_mode='threading',  # 使用线程模式
    ping_timeout=60,         # ping超时时间
    ping_interval=25,        # ping间隔
    engineio_logger=True,    # 启用引擎日志以便调试
    logger=True,             # 启用SocketIO日志以便调试
    manage_session=False,    # 不使用Flask会话管理
    always_connect=True,     # 总是允许连接
    max_http_buffer_size=1e8 # 增加HTTP缓冲区大小
)

# 导入路由
from app.controllers.event_controller import event_bp
app.register_blueprint(event_bp, url_prefix='/api/event')

# 导入认证路由
from app.controllers.auth_controller import auth_bp
app.register_blueprint(auth_bp, url_prefix='/api/auth')

# 导入WebSocket事件处理
from app.controllers.socket_controller import register_socket_events
register_socket_events(socketio)

# 定义登录检查装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 从多个来源获取Token
        token = None
        
        # 1. 尝试从Authorization头部获取
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        # 2. 尝试从Cookie获取
        if not token:
            token = request.cookies.get('access_token')
            
        # 3. 尝试从查询参数获取（不推荐，但为了兼容）
        if not token:
            token = request.args.get('access_token')
        
        if token:
            try:
                # 验证令牌有效性
                app.config['JWT_TOKEN_LOCATION'] = ['headers']  # 临时设置为仅从头部获取
                app.config['JWT_HEADER_NAME'] = 'Authorization'
                app.config['JWT_HEADER_TYPE'] = 'Bearer'
                
                # 手动解码Token
                jwt_data = decode_token(token)
                identity = jwt_data['sub']
                
                # 如果到这里没有异常，则用户已登录
                return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"Token验证失败: {str(e)}")
                pass  # Token无效，继续执行重定向逻辑
        
        # Token不存在或无效
        if request.path.startswith('/api/'):
            return jsonify({
                'status': 'error',
                'message': '请先登录',
                'authenticated': False
            }), 401
            
        # 如果是页面请求，重定向到登录页
        return redirect(url_for('login'))
    
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/warroom/<event_id>')
@login_required
def warroom(event_id):
    return render_template('warroom.html', event_id=event_id)

@app.route('/health')
def health():
    return jsonify({
        'status': 'success',
        'message': 'DeepSOC API is healthy'
    })

# @app.route('/result')
# def result():
#     return render_template('heimdallite.html')
@app.route('/result')
def result():
    inspec_dir = r'./output/inspec'
    json_files = [f for f in os.listdir(inspec_dir) if f.endswith('.json')]
    if not json_files:
        return render_template('heimdallite.html', auto_json=None, auto_json_filename=None)
    json_files = [os.path.join(inspec_dir, f) for f in json_files]
    latest_file = max(json_files, key=os.path.getmtime)
    with open(latest_file, 'r', encoding='utf-8') as f:
        try:
            json_data = f.read()
        except Exception as e:
            return render_template('heimdallite.html', auto_json=None, auto_json_filename=None)
    return render_template('heimdallite.html', auto_json=json_data, auto_json_filename=os.path.basename(latest_file))


def create_tables():
    """创建所有数据库表"""
    with app.app_context():
        db.create_all()
        logger.info("数据库表创建成功")

def create_admin_user():
    """创建默认的管理员用户(如果不存在)"""
    with app.app_context():
        # 检查是否已存在管理员
        admin_exists = User.query.filter_by(role='admin').first()
        if admin_exists:
            logger.info("管理员用户已存在，无需创建")
            return False
        
        # 获取环境变量中的管理员信息
        admin_username = os.getenv('ADMIN_USERNAME', 'admin')
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
        admin_email = os.getenv('ADMIN_EMAIL', 'admin@deepsoc.local')
        
        try:
            # 创建管理员用户
            admin_user = User(
                username=admin_username,
                email=admin_email,
                role='admin'
            )
            admin_user.set_password(admin_password)
            
            # 保存到数据库
            db.session.add(admin_user)
            db.session.commit()
            
            logger.info(f"默认管理员账户创建成功: {admin_username}")
            return True
        except Exception as e:
            db.session.rollback()
            logger.error(f"创建默认管理员账户失败: {str(e)}")
            return False

def start_agent(role):
    """启动特定角色的Agent"""
    logger.info(f"启动 {role} Agent")
    if role == '_captain':
        from app.services.captain_service import run_captain
        run_captain()
    elif role == '_manager':
        from app.services.manager_service import run_manager
        run_manager()
    elif role == '_operator':
        from app.services.operator_service import run_operator
        run_operator()
    elif role == '_executor':
        from app.services.executor_service import run_executor
        run_executor()
    elif role == '_expert':
        from app.services.expert_service import run_expert
        run_expert()
    else:
        logger.error(f"未知角色: {role}")
        sys.exit(1)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='DeepSOC - AI驱动的安全运营中心')
    parser.add_argument('-role', type=str, help='Agent角色: _captain, _manager, _operator, _executor, _expert')
    parser.add_argument('-init', action='store_true', help='初始化数据库')
    args = parser.parse_args()
    
    if args.init:
        create_tables()
        create_admin_user()
    
    if args.role:
        start_agent(args.role)
    else:
        # 启动Web服务器，添加更多选项
        socketio.run(
            app, 
            host=os.getenv('LISTEN_HOST', '0.0.0.0'), 
            port=int(os.getenv('LISTEN_PORT', 55555)),
            debug=True,
            use_reloader=False,  # 禁用重载器，避免Socket.IO连接问题
            allow_unsafe_werkzeug=True  # 允许在调试模式下使用Werkzeug
        ) 