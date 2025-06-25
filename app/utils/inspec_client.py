import subprocess
import json
import os
import logging
import time
import yaml
import sys
from typing import Optional, Dict, Any, List, Union

# 添加项目根目录到系统路径，以便直接运行时能够正确导入模块
if __name__ == '__main__':
    # 获取当前文件的绝对路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # 获取项目根目录（假设当前文件在 app/utils 目录下）
    project_root = os.path.abspath(os.path.join(current_dir, '../..'))
    # 将项目根目录添加到系统路径
    sys.path.insert(0, project_root)

# 获取项目根目录的绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '../..'))

from app.config import config

logger = logging.getLogger(__name__)

class InspecClient:
    def __init__(self):
        self.profiles_config = self._load_profile_config()
        self.inspec_path = config.INSPEC_PATH
        self.profile_dir = os.path.join(project_root, config.INSPEC_PROFILE_DIR)
        self.output_dir = os.path.join(project_root, config.INSPEC_OUTPUT_DIR)
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
    def _load_profile_config(self) -> Dict[int, Dict[str, Any]]:
        """
        加载脚本配置
        """
        try:
            prompts_path = os.path.join(project_root, 'app/prompts/background_inspec_scripts.md')
            with open(prompts_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # print(content)
                # 提取YAML部分
                yaml_content = content.split('```yaml')[1].split('```')[0]
                profiles_data = yaml.safe_load(yaml_content)
                
                # 将脚本列表转换为以ID为键的字典
                profiles_dict = {p['id']: p for p in profiles_data.get('profiles', [])}
                logger.info(f"成功加载 {len(profiles_dict)} 个脚本配置")
                return profiles_dict
        except Exception as e:
            logger.error(f"加载脚本配置失败: {str(e)}")
            return {}

    def get_profile_info(self, profile_id: int) -> Optional[Dict[str, Any]]:
        """
        获取脚本信息
        :param playbook_id: 脚本ID
        :return: 脚本信息
        """
        return self.profiles_config.get(profile_id)

    def list_profiles(self) -> List[Dict[str, Any]]:
        """
        列出所有可用的脚本
        :return: 脚本列表
        """
        return list(self.profiles_config.values())

    def execute_profile(self, profile_id: int, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Inspec脚本
        :param profile_id: 脚本ID
        :param params: 脚本参数
        :return: 执行结果
        """
        profile = self.get_profile_info(profile_id)
        if not profile:
            logger.error(f"脚本不存在: {profile_id}")
            return {"status": "error", "message": f"脚本不存在: {profile_id}"}

        # 验证必要参数
        missing_params = []
        for param in profile.get('params', []):
            if param.get('required', False) and param['name'] not in params:
                missing_params.append(param['name'])
        
        if missing_params:
            logger.error(f"缺少必要参数: {', '.join(missing_params)}")
            return {"status": "error", "message": f"缺少必要参数: {', '.join(missing_params)}"}

        # 设置默认参数
        for param in profile.get('params', []):
            if param['name'] not in params and 'default' in param:
                params[param['name']] = param['default']

        # 如果没有指定输出路径，自动生成一个
        if 'output_path' not in params:
            timestamp = time.strftime("%Y%m%d%H%M%S")
            params['output_path'] = os.path.join(self.output_dir, f"{profile['name']}_{timestamp}.{params.get('output_format', 'json')}")
        else:
            # 如果指定了相对路径，转换为绝对路径
            if not os.path.isabs(params['output_path']):
                params['output_path'] = os.path.join(project_root, params['output_path'])

        # 构建Inspec命令
        cmd = self._build_inspec_command(profile, params)
        if not cmd:
            return {"status": "error", "message": "构建命令失败"}

        # 执行命令
        logger.info(f"执行脚本: {profile['name']}, 命令: {' '.join(cmd)}")
        try:
            result = self._run_command(cmd)
            
            # 如果成功，并且输出文件存在，尝试读取结果
            if result["status"] == "success" and os.path.exists(params['output_path']):
                try:
                    with open(params['output_path'], 'r', encoding='utf-8') as f:
                        if params.get('output_format', 'json') == 'json':
                            result["result"] = json.load(f)
                        else:
                            result["result"] = f.read()
                except Exception as e:
                    logger.warning(f"读取输出文件失败: {str(e)}")
            
            return result
        except Exception as e:
            logger.error(f"脚本执行失败: {str(e)}")
            return {"status": "error", "message": f"脚本执行失败: {str(e)}"}

    def _build_inspec_command(self, profile: Dict[str, Any], params: Dict[str, Any]) -> List[str]:
        """
        构建Inspec命令
        :param profile: 脚本信息
        :param params: 参数信息
        :return: 命令列表
        """
        try:
            cmd = [self.inspec_path, "exec"]
            
            # 添加脚本路径
            script_path = params.get('script_path')
            if not script_path:
                # 使用默认值，并确保是完整路径
                default_path = None
                for param in profile.get('params', []):
                    if param['name'] == 'script_path' and 'default' in param:
                        default_path = param['default']
                        break
                
                if default_path:
                    # 如果默认路径是相对路径，转换为绝对路径
                    if not os.path.isabs(default_path):
                        script_path = os.path.join(project_root, default_path)
                    else:
                        script_path = default_path
                else:
                    logger.error("未指定脚本路径")
                    return []
            elif not os.path.isabs(script_path):
                # 如果脚本路径是相对路径，转换为绝对路径
                script_path = os.path.join(project_root, script_path)
            
            cmd.append(script_path)
            
            # 添加目标主机
            host = params.get('host')
            user = params.get('user')
            if host:
                target = f"ssh://"
                if user:
                    target += f"{user}@"
                target += host
                cmd.extend(["-t", target])
            
            # 添加输出格式
            output_format = params.get('output_format', 'json')
            cmd.extend(["--reporter", output_format])
            
            # 添加输出路径
            output_path = params.get('output_path')
            if output_path:
                cmd.extend([">", output_path])
            
            return cmd
        except Exception as e:
            logger.error(f"构建命令失败: {str(e)}")
            return []

    def _run_command(self, cmd: List[str]) -> Dict[str, Any]:
        """
        运行命令
        :param cmd: 命令列表
        :return: 执行结果
        """
        try:
            # 注释掉实际执行命令的部分
            # process = subprocess.Popen(
            #     cmd,
            #     stdout=subprocess.PIPE,
            #     stderr=subprocess.PIPE,
            #     text=True
            # )
            # stdout, stderr = process.communicate()
            
            # 使用logger打印命令
            command_str = " ".join(cmd)
            logger.info(f"[模拟执行] 命令: {command_str}")
            
            # 模拟成功执行
            # if process.returncode == 0:
            logger.info("命令模拟执行成功")
            return {
                "status": "success",
                "output": "模拟执行输出",
                "command": command_str
            }
            # else:
            #     logger.error(f"命令执行失败: {stderr}")
            #     return {
            #         "status": "error",
            #         "message": stderr,
            #         "command": " ".join(cmd)
            #     }
        except Exception as e:
            logger.error(f"命令执行异常: {str(e)}")
            return {
                "status": "error",
                "message": str(e),
                "command": " ".join(cmd)
            }

    def wait_for_completion(self, process_id: Union[str, int], interval: int = 5) -> Dict[str, Any]:
        """
        兼容旧接口，等待进程完成
        :param process_id: 进程ID
        :param interval: 检查间隔
        :return: 执行结果
        """
        logger.warning("wait_for_completion方法已弃用，Inspec命令为同步执行")
        return {
            "status": "warning",
            "message": "wait_for_completion方法已弃用，Inspec命令为同步执行"
        } 

if __name__ == '__main__':
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建InspecClient实例
    client = InspecClient()
    
    # 列出所有可用的脚本
    profiles = client.list_profiles()
    logger.info(f"可用脚本列表: {json.dumps(profiles, ensure_ascii=False, indent=2)}")
    
    # 如果有可用脚本，尝试执行第一个
    if profiles:
        profile_id = profiles[0]['id']
        logger.info(f"尝试执行脚本ID: {profile_id}")
        
        # 构建测试参数
        params = {
            'output_format': 'json',
            'output_path': 'output/inspec/test.json',
            'host': 'example.com',
            'user': 'test_user'
        }
        
        # 执行脚本
        result = client.execute_profile(profile_id, params)
        logger.info(f"执行结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        logger.warning("没有找到可用的脚本") 