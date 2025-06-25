import os
import json
from pathlib import Path
import yaml

class PromptService:
    def __init__(self, role=None):
        self.prompt_dir = Path(__file__).parent.parent / 'prompts'
        self.role = role
        self._prompts = {}
        self._load_prompts()

    def _load_prompts(self):
        """加载所有提示词"""
        # 加载背景信息
        with open(self.prompt_dir / 'background_security.md', 'r', encoding='utf-8') as f:
            background_info = f.read()

        # 加载剧本列表
        with open(self.prompt_dir / 'background_inspec_scripts.md', 'r', encoding='utf-8') as f:
            script_list = f.read()

        # 角色文件映射
        role_files = {
            '_captain': 'role_soc_captain.md',
            '_manager': 'role_soc_manager.md',
            '_operator': 'role_soc_operator.md',
            '_expert': 'role_soc_expert.md'
            
        }
        
        # 加载各角色提示词
        for role, file_name in role_files.items():
            prompt_file = self.prompt_dir / file_name
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    prompt = f.read()
                    # 替换背景信息和剧本列表
                    prompt = prompt.replace('{background_info}', background_info)
                    prompt = prompt.replace('{script_list}', script_list)
                    self._prompts[role] = prompt
            else:
                print(f"警告：角色提示词文件 {file_name} 不存在")

    def get_system_prompt(self, role=None):
        """获取指定角色的系统提示词"""
        role_to_use = role if role else self.role
        return self._prompts.get(role_to_use, f"你是SOC团队中的一名{role_to_use}，请根据背景信息和上下文，参与事件响应。")