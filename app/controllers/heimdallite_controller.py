from flask import Blueprint, render_template
import os
import json

heimdallite_bp = Blueprint('heimdallite', __name__)

@heimdallite_bp.route('/heimdallite')
def heimdallite():
    inspec_dir = r'../../output/inspec'
    # 获取所有json文件
    json_files = [f for f in os.listdir(inspec_dir) if f.endswith('.json')]
    print('json_files:', json_files)
    if not json_files:
        return render_template('heimdallite.html', auto_json=None, auto_json_filename=None)
    # 找到最新的json文件
    json_files = [os.path.join(inspec_dir, f) for f in json_files]
    latest_file = max(json_files, key=os.path.getmtime)
    # 读取json内容
    with open(latest_file, 'r', encoding='utf-8') as f:
        try:
            json_data = f.read()
        except Exception as e:
            return render_template('heimdallite.html', auto_json=None, auto_json_filename=None)
    print('auto_json:', json_data is not None)
    return render_template('heimdallite.html', auto_json=json_data, auto_json_filename=os.path.basename(latest_file)) 