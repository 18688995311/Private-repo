# openclaw_ops — Claude Code 使用说明

## 日常提交流程

一条命令搞定：
```bash
git add -A && git commit -m "你的描述" && git push
```

或者分步执行：
```bash
cd /Users/javis/Workspace/openclaw_ops

git add -A
git commit -m "简短描述你改了什么"
git push
```

## 自动备份（文件变动自动提交）

启动监听（后台持续运行，改完脚本秒提交）：
```bash
bash /Users/javis/Workspace/openclaw_ops/scripts/auto-git-watch.sh
```

- 监听范围：`scripts/` 目录
- 触发条件：文件有改动即自动 `add → commit → push`
- commit 信息格式：`auto: scripts updated @ 2026-03-01 14:30:00`
- 停止：`Ctrl+C`

## 常用 git 操作

```bash
# 查看改动了哪些文件
git status

# 查看具体改动内容
git diff

# 查看提交历史
git log --oneline

# 只提交指定文件
git add scripts/tgb/xxx.py
git commit -m "fix: 修了xxx"
git push
```

## 远程仓库

- 地址：`git@github.com:18688995311/Private-repo.git`
- 分支：`main`
- 权限：Private

## SSH 说明

- Key 类型：`ed25519`
- 文件：`~/.ssh/id_ed25519`
- 已加入 macOS Keychain，重启后无需重新 ssh-add

如果重启后 push 报权限错误，执行：
```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

## .gitignore 已屏蔽

| 类型 | 规则 |
|------|------|
| 密钥 | `.env` `*.key` `*.pem` |
| 运行产物 | `runs/` `tmp/` `*.log` |
| Python | `.venv/` `__pycache__/` `*.pyc` |
| Node | `node_modules/` |
| Mac | `.DS_Store` |
