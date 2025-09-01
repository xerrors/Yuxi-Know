from neo4j import GraphDatabase
from neo4j.exceptions import AuthError, ServiceUnavailable

# sudo ln -s /snap/core22/1586/usr/sbin/iptables /usr/sbin/iptables


def check_neo4j_status(uri="bolt://localhost:7687", username="neo4j", password="0123456789"):
    """
    检查 Neo4j 数据库是否可以连接并正常工作。

    参数:
        uri (str): Neo4j 的 URI，默认为 "bolt://localhost:7687"
        username (str): 数据库用户名，默认为 "neo4j"
        password (str): 数据库密码，默认为 "0123456789"

    返回:
        str: "OK" 表示连接成功，"UNAVAILABLE" 表示服务不可用，"AUTH_FAILED" 表示认证失败。
    """
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
        with driver.session() as session:
            # 简单的查询来测试连接
            result = session.run("RETURN 1")
            if result.single()[0] == 1:
                return "OK"
    except ServiceUnavailable:
        return "UNAVAILABLE"
    except AuthError:
        return "AUTH_FAILED"
    finally:
        # 确保关闭驱动
        driver.close()


# 测试函数
status = check_neo4j_status()
print(f"Neo4j status: {status}")
