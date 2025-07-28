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

def clean_output(output: str) -> str:
    # 如果包含 '{'，则截取从第一个 '{' 开始的部分；否则返回原始内容
    index = output.find('{')
    return output[index:] if index != -1 else output

class InspecClient:
    def __init__(self):
        self.profiles_config = self._load_profile_config()
        # 使用Docker方式运行InSpec
        self.use_docker = True
        self.inspec_path = config.INSPEC_PATH if not self.use_docker else "docker"
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
            result = self._run_command(cmd, params.get('output_path'))
            
            # 如果成功，尝试解析stdout中的结果（当输出格式为json时）
            if result["status"] == "success" and result.get("stdout"):
                try:
                    if params.get('output_format', 'json') == 'json':
                        # 尝试解析JSON输出
                        result["result"] = json.loads(result["stdout"])
                    else:
                        result["result"] = result["stdout"]
                except json.JSONDecodeError as e:
                    logger.warning(f"解析JSON输出失败: {str(e)}")
                    result["result"] = result["stdout"]
                except Exception as e:
                    logger.warning(f"处理输出失败: {str(e)}")
            
            # 如果指定了输出文件且执行成功，将结果写入文件
            if result["status"] == "success" and params.get('output_path') and result.get("stdout"):
                try:
                    os.makedirs(os.path.dirname(params['output_path']), exist_ok=True)
                    with open(params['output_path'], 'w', encoding='utf-8') as f:
                        f.write(result["stdout"])
                    logger.info(f"结果已保存到: {params['output_path']}")
                except Exception as e:
                    logger.warning(f"保存输出文件失败: {str(e)}")
            
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
            if self.use_docker:
                # Docker方式运行InSpec
                cmd = [
                    "docker", "run", "--rm",
                    "-e", "CHEF_LICENSE=accept",
                    "-v", f"{project_root}:/share",
                    "chef/inspec", "exec"
                ]
                
                # 添加脚本路径（Docker容器内的路径）
                script_path = params.get('script_path')
                if not script_path:
                    # 使用默认值
                    default_path = None
                    for param in profile.get('params', []):
                        if param['name'] == 'script_path' and 'default' in param:
                            default_path = param['default']
                            break
                    
                    if default_path:
                        script_path = f"/share/{default_path}"
                    else:
                        logger.error("未指定脚本路径")
                        return []
                else:
                    # 如果是绝对路径，需要转换为容器内路径
                    if os.path.isabs(script_path):
                        # 将绝对路径转换为相对于项目根目录的路径
                        rel_path = os.path.relpath(script_path, project_root)
                        script_path = f"/share/{rel_path}"
                    else:
                        script_path = f"/share/{script_path}"
                
                cmd.append(script_path)
            else:
                # 本地安装的InSpec
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
            
            # 添加目标主机，支持用户名和密码
            host = params.get('host')
            user = params.get('user')
            password = params.get('password')
            
            if host:
                target = f"ssh://"
                if user:
                    target += f"{user}"
                    if password:
                        target += f":{password}"
                    target += "@"
                target += host
                cmd.extend(["-t", target])
            
            # 添加输出格式
            output_format = params.get('output_format', 'json')
            cmd.extend(["--reporter", output_format])
            
            # # 对于MySQL baseline，需要添加特定的输入参数
            # if 'mysql' in profile.get('name', '').lower():
            #     mysql_user = params.get('mysql_user', 'root')
            #     mysql_password = params.get('mysql_password', 'iloverandompasswordsbutthiswilldo')
            #     cmd.extend([
            #         "--input", f"user={mysql_user}",
            #         "--input", f"password={mysql_password}"
            #     ])
            
            return cmd
        except Exception as e:
            logger.error(f"构建命令失败: {str(e)}")
            return []

    def _run_command(self, cmd: List[str], output_path: Optional[str] = None) -> Dict[str, Any]:
        """
        运行命令
        :param cmd: 命令列表
        :return: 执行结果
        """
        try:
            command_str = " ".join(cmd)
            logger.info(f"执行命令: {command_str}")
            
            # 实际执行命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False
            )
            stdout, stderr = process.communicate()
            
            # InSpec返回码说明:
            # 0 = 所有测试通过
            # 100 = 有测试失败但程序正常执行
            # 101 = 有测试跳过但程序正常执行  
            # 其他值 = 程序执行异常
            success_codes = [0, 100, 101]
            
            result = {
                "command": command_str,
                "return_code": process.returncode,
                "stdout": clean_output(stdout),
                "stderr": clean_output(stderr)
            }
            
            if process.returncode in success_codes:
                logger.info(f"命令执行成功，返回码: {process.returncode}")
                result["status"] = "success"
                result["output"] = stdout
            else:
                logger.error(f"命令执行失败，返回码: {process.returncode}")
                result["status"] = "error"
                result["message"] = f"InSpec执行失败，返回码: {process.returncode}"
                if stderr:
                    result["message"] += f", 错误信息: {stderr}"
            
            return result
            
        except Exception as e:
            logger.error(f"命令执行异常: {str(e)}")
            return {
                "status": "error",
                "message": f"命令执行异常: {str(e)}",
                "command": " ".join(cmd),
                "return_code": -1,
                "stdout": "",
                "stderr": str(e)
            }

    def wait_for_completion(self, process_id: Union[str, int], interval: int = 5) -> Dict[str, Any]:
        """
        兼容旧接口，等待进程完成
        :param process_id: 进程ID
        :param interval: 检查间隔
        :return: 执行结果
        """
        # 避免未使用参数警告
        _ = process_id, interval
        
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
        profile_id = profiles[2]['id']
        logger.info(f"尝试执行脚本ID: {profile_id}")
        
        # 构建测试参数
        params = {
            'output_format': 'json',
            'output_path': 'output/inspec/test.json',
            # 'host': 'example.com',
            # 'user': 'test_user',
            # 'password': 'test_password'  # 添加密码参数
        }
        
        # 执行脚本
        result = client.execute_profile(profile_id, params)
        # logger.info(f"执行结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
    else:
        logger.warning("没有找到可用的脚本") 