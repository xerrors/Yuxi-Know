"""
用户ID生成工具
提供用户名验证和user_id自动生成功能
"""

import re

try:
    from pypinyin import lazy_pinyin, Style
    PYPINYIN_AVAILABLE = True
except ImportError:
    PYPINYIN_AVAILABLE = False


def to_pinyin(text: str) -> str:
    """
    将中文转换为拼音
    优先使用pypinyin库，如果不可用则使用简化版本
    """
    if PYPINYIN_AVAILABLE:
        # 使用pypinyin进行转换
        pinyin_list = lazy_pinyin(text, style=Style.NORMAL)
        return ''.join(pinyin_list)
    else:
        # 简化的拼音映射表（备用方案）
        pinyin_map = {
            '张': 'zhang', '王': 'wang', '李': 'li', '刘': 'liu', '陈': 'chen',
            '杨': 'yang', '赵': 'zhao', '黄': 'huang', '周': 'zhou', '吴': 'wu',
            '徐': 'xu', '孙': 'sun', '胡': 'hu', '朱': 'zhu', '高': 'gao',
            '林': 'lin', '何': 'he', '郭': 'guo', '马': 'ma', '罗': 'luo',
            '梁': 'liang', '宋': 'song', '郑': 'zheng', '谢': 'xie', '韩': 'han',
            '唐': 'tang', '冯': 'feng', '于': 'yu', '董': 'dong', '萧': 'xiao',
            '程': 'cheng', '曹': 'cao', '袁': 'yuan', '邓': 'deng', '许': 'xu',
            '傅': 'fu', '沈': 'shen', '曾': 'zeng', '彭': 'peng', '吕': 'lv',
            '苏': 'su', '卢': 'lu', '蒋': 'jiang', '蔡': 'cai', '贾': 'jia',
            '丁': 'ding', '魏': 'wei', '薛': 'xue', '叶': 'ye', '阎': 'yan',
            '余': 'yu', '潘': 'pan', '杜': 'du', '戴': 'dai', '夏': 'xia',
            '钟': 'zhong', '汪': 'wang', '田': 'tian', '任': 'ren', '姜': 'jiang',
            '范': 'fan', '方': 'fang', '石': 'shi', '姚': 'yao', '谭': 'tan',
            '廖': 'liao', '邹': 'zou', '熊': 'xiong', '金': 'jin', '陆': 'lu',
            '郝': 'hao', '孔': 'kong', '白': 'bai', '崔': 'cui', '康': 'kang',
            '毛': 'mao', '邱': 'qiu', '秦': 'qin', '江': 'jiang', '史': 'shi',
            '顾': 'gu', '侯': 'hou', '邵': 'shao', '孟': 'meng', '龙': 'long',
            '万': 'wan', '段': 'duan', '漕': 'cao', '钱': 'qian', '汤': 'tang',
            # 添加一些常用字
            '小': 'xiao', '大': 'da', '明': 'ming', '强': 'qiang', '文': 'wen',
            '华': 'hua', '建': 'jian', '国': 'guo', '军': 'jun', '伟': 'wei',
            '超': 'chao', '雷': 'lei', '鹏': 'peng', '俊': 'jun', '敏': 'min',
            '志': 'zhi', '勇': 'yong', '杰': 'jie', '涛': 'tao', '斌': 'bin',
            '辉': 'hui', '阳': 'yang', '磊': 'lei', '刚': 'gang',
            '飞': 'fei', '翔': 'xiang', '波': 'bo', '峰': 'feng', '凯': 'kai',
            '静': 'jing', '丽': 'li', '秀': 'xiu', '红': 'hong', '霞': 'xia',
            '洁': 'jie', '燕': 'yan', '艳': 'yan', '娟': 'juan', '玲': 'ling',
            '琳': 'lin', '萍': 'ping', '芳': 'fang', '莉': 'li', '婷': 'ting',
            '慧': 'hui', '娜': 'na', '丹': 'dan', '青': 'qing', '倩': 'qian',
        }

        result = []
        for char in text:
            if char in pinyin_map:
                result.append(pinyin_map[char])
            elif char.isalpha():
                result.append(char.lower())
            elif char.isdigit():
                result.append(char)
            # 忽略其他字符

        return ''.join(result)


def validate_username(username: str) -> tuple[bool, str]:
    """
    验证用户名格式

    Args:
        username: 用户名

    Returns:
        Tuple[bool, str]: (是否有效, 错误信息)
    """
    if not username:
        return False, "用户名不能为空"

    if len(username) < 2:
        return False, "用户名长度不能少于2个字符"

    if len(username) > 20:
        return False, "用户名长度不能超过20个字符"

    # 检查是否包含不允许的字符
    # 允许中文、英文、数字、下划线
    if not re.match(r'^[\u4e00-\u9fa5a-zA-Z0-9_]+$', username):
        return False, "用户名只能包含中文、英文、数字和下划线"

    return True, ""


def generate_user_id(username: str) -> str:
    """
    根据用户名生成user_id

    Args:
        username: 用户名

    Returns:
        str: 生成的user_id
    """
    # 1. 基本清理
    username = username.strip()

    # 2. 转换为拼音（如果包含中文）
    user_id = to_pinyin(username)

    # 3. 处理特殊字符，只保留字母、数字和下划线
    user_id = re.sub(r'[^a-zA-Z0-9_]', '', user_id)

    # 4. 确保不以数字开头
    if user_id and user_id[0].isdigit():
        user_id = 'u' + user_id

    # 5. 如果为空或太短，使用默认前缀
    if len(user_id) < 2:
        user_id = 'user' + str(hash(username) % 10000).zfill(4)

    # 6. 长度限制
    if len(user_id) > 20:
        user_id = user_id[:20]

    return user_id.lower()


def generate_unique_user_id(username: str, existing_user_ids: list[str]) -> str:
    """
    生成唯一的user_id，如果重复则添加数字后缀

    Args:
        username: 用户名
        existing_user_ids: 已存在的user_id列表

    Returns:
        str: 唯一的user_id
    """
    base_user_id = generate_user_id(username)

    # 如果不重复，直接返回
    if base_user_id not in existing_user_ids:
        return base_user_id

    # 如果重复，添加数字后缀
    counter = 1
    while True:
        candidate = f"{base_user_id}{counter}"
        if candidate not in existing_user_ids:
            return candidate
        counter += 1

        # 防止无限循环
        if counter > 9999:
            # 使用时间戳作为后缀
            import time
            candidate = f"{base_user_id}{int(time.time()) % 10000}"
            return candidate


def is_valid_phone_number(phone: str) -> bool:
    """
    验证手机号格式（支持中国大陆手机号）

    Args:
        phone: 手机号字符串

    Returns:
        bool: 是否为有效手机号
    """
    if not phone:
        return False

    # 移除空格和特殊字符
    phone = re.sub(r'[\s\-\(\)]', '', phone)

    # 中国大陆手机号格式：1开头，第二位是3-9，总共11位
    pattern = r'^1[3-9]\d{9}$'

    return bool(re.match(pattern, phone))


def normalize_phone_number(phone: str) -> str:
    """
    标准化手机号格式

    Args:
        phone: 原始手机号

    Returns:
        str: 标准化后的手机号
    """
    if not phone:
        return ""

    # 移除所有非数字字符
    phone = re.sub(r'\D', '', phone)

    # 如果是中国大陆手机号，确保格式正确
    if len(phone) == 11 and phone.startswith('1'):
        return phone

    return phone
