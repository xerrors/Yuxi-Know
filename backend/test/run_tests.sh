#!/bin/bash

# 测试脚本运行器
# 提供快速运行不同类型测试的方法

echo "Yuxi-Know API 测试运行器"
echo "========================"

# 检查测试服务是否运行
check_server() {
    echo "检查测试服务器状态..."
    curl -s http://localhost:5050/api/system/health > /dev/null 2>&1
    if [ $? -eq 0 ]; then
        echo "✓ 测试服务器运行正常"
        return 0
    else
        echo "✗ 警告: 测试服务器未运行或无法访问"
        echo "  请确保服务器在 http://localhost:5050 运行"
        return 1
    fi
}

# 运行所有测试
run_all_tests() {
    echo "运行所有API测试..."
    uv run pytest test/api/ -v
}

# 运行认证测试
run_auth_tests() {
    echo "运行认证API测试..."
    uv run pytest test/api/test_auth_api.py -v
}

# 运行系统测试
run_system_tests() {
    echo "运行系统API测试..."
    uv run pytest test/api/test_system_api.py -v
}

# 运行对话测试
run_chat_tests() {
    echo "运行对话API测试..."
    uv run pytest test/api/test_chat_api.py -v
}

# 运行快速测试（只测试基础功能）
run_quick_tests() {
    echo "运行快速测试（基础功能）..."
    uv run pytest test/api/ -v -m "not slow"
}

# 显示帮助
show_help() {
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  all     - 运行所有测试"
    echo "  auth    - 运行认证测试"
    echo "  system  - 运行系统测试"
    echo "  chat    - 运行对话测试"
    echo "  quick   - 运行快速测试（排除慢速测试）"
    echo "  check   - 检查服务器状态"
    echo "  help    - 显示此帮助"
    echo ""
    echo "示例:"
    echo "  $0 all       # 运行所有测试"
    echo "  $0 quick     # 快速测试"
    echo "  $0 check     # 检查服务器"
}

# 主逻辑
case "${1:-all}" in
    "all")
        check_server
        run_all_tests
        ;;
    "auth")
        check_server
        run_auth_tests
        ;;
    "system")
        check_server
        run_system_tests
        ;;
    "chat")
        check_server
        run_chat_tests
        ;;
    "quick")
        check_server
        run_quick_tests
        ;;
    "check")
        check_server
        ;;
    "help"|"-h"|"--help")
        show_help
        ;;
    *)
        echo "未知选项: $1"
        show_help
        exit 1
        ;;
esac