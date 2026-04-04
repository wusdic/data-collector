#!/bin/bash
# 推送到 GitHub 的脚本

# 1. 在 GitHub 上创建仓库后，运行此脚本

# 设置远程仓库（请替换为你的用户名）
GITHUB_USERNAME="your-github-username"

# 添加远程仓库
git remote add origin https://github.com/${GITHUB_USERNAME}/data-collector.git

# 推送代码
git push -u origin master

echo "✅ 推送完成!"
echo ""
echo "请访问 https://github.com/${GITHUB_USERNAME}/data-collector 查看"
