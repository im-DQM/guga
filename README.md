# 咕嘎（guga）

一个人的私人云端 Agent 系统：一套自建的 web 外壳 + 若干个各管一摊的「咕嘎」+ 知识库。
跑在一台腾讯云服务器上，单用户自用。这个仓库是**脱敏后的源码与文档**——密码、密钥、会话、上传文件都不在里面。

## 目录

    site/             hub 网站（Caddy 静态托管）
      index.html      桌面版主界面（聊天、待办、计划、成就徽章）
      m.html          手机版
      group.html      咕嘎群
      plan.html       计划 / 徽章墙
      join.html       他机接入（网页授权）
      login.html      门卫登录页
      *.py            页面生成脚本

    platform/         后端服务
      Caddyfile       反代与门卫（forward_auth）
      docker-compose.yml
      todo_service/   待办 API（todos.md 读写、打卡、段位与徽章、门卫校验）
      remote/         远程操作 API（ssh 到他机、接入台账、站点清单）
      jiaxin_service/ 「我的夹心」存储 API
      term/           网页终端（ttyd + tmux）

    guga-system/      咕嘎们自己
      guga/guga0..8/  每个咕嘎三件套：SOUL.md（我是谁）、MEMORY.md（记忆）、
                      WORKFLOW.md（工作流 + 经验）、journal/（日记）
      scripts/        日常脚本（todo.py、guga.py 调度、idea_pool.py、简报…）
      knowledge/      知识分区（procedures.md、projects/、价值观、饮食…）

    docs/             项目图纸与进度

## 九个咕嘎

| 编号 | 干什么 |
| --- | --- |
| 0 | 编码主力，在 ~/workspace 里跑 Claude Code，编码规则归他 |
| 1 | 管家：网站、待办与简报、远程操作、记忆与知识、夜间自动化 |
| 2 | 飞书（已停用，编号不回收） |
| 3 | WorkBuddy：PPT / Word / Excel / PDF 等文件级成品 |
| 4 | LightVela：推消息到手机、建站、GitHub 直连 |
| 5 | ASUS 笔记本（win-asus），只记那台机器的事 |
| 6 | 接入记录官：谁接进来、怎么连、干了什么 |
| 7 | 斥候：热点侦察、找料，候选进想法池 |
| 8 | 保安：swap / 内存 / 残留 / 服务健康巡检与垃圾回收 |

**调用方式**：聊天里 `/N` 开头就是派给咕嘎 N 号（N=0…8），没前缀归一号；一号负责调用、汇总与回写。
每个咕嘎干完活往自己的 journal 记一笔，值得固化的经验写进自己 WORKFLOW.md 的「经验」段，周复盘再并进正文。

## 部署（自用）

    # 依赖：docker + docker compose、python3、Caddy（容器）、systemd
    cd ~/stack && docker compose up -d          # caddy（+ gitea，已默认停用）
    sudo systemctl enable --now hermes-todo-api guga-remote-api guga-join-api guga-term-api

本站点整套挂门卫（`/login.html` + 签名 cookie），账号哈希与签名密钥放服务器 `~/.hermes/secrets/`，**不入库**。

## 没进仓库的东西

- `~/.hermes/secrets/`（门卫账号哈希、签名密钥）、各类 token
- 会话与状态文件（`sessions.json`、`sites.json`、`group.json`、`state/`）
- 上传与备份（`hub/uploads/`、`stack/backups/`）、日志、`*.bak`
- 模型权重（`models/chat/*.gguf`）、构建产物

## 许可证

私人项目，未授权请勿使用。代码里引用的第三方模板（如简历 LaTeX 模板）版权归原作者。
