侍魂 6 原生重构 — 当前进度（2026-11-20）

工作目录：/Users/xargin/Projects/samsho6-native
代码、资源副本、构建产物与缓存全部留在本目录，不写 Documents / iCloud。
目标：按用户日版 PS2 镜像逐项还原全部机制。C++20 + SDL3，无大型游戏引擎，
运行时不依赖 PS2 模拟器或 BIOS。完整 1:1 游戏尚未完成。

现在可以运行的连续对战
双击 cpu.command 可直接用 P1 霸王丸对战电脑霸王丸。想换人可运行 ./select.command --cpu p2，在选人画面用两席按键选好角色，开战后由电脑接管 2P。启动参数 --cpu p1 或 --cpu both 分别可指定电脑控制 1P 或两席。试玩入口的角色 AI 等级设为 4，赛后菜单仍用原来的按键操作。
连续防御时，电脑在格挡硬直期间沿用上一击的站防或蹲防高度，玩家可以用方向键改变防守高度。双方被刀击和冰弹连续压制的原版对照见 cpu-guard-followups.json。
双击 /Users/xargin/Projects/samsho6-native/battle.command。单独使用 native-viewer 包时，在包内执行 ./run.command --mode versus。
角色登场 → 首局字幕 → 本地双人对战 → KO、双KO或时间到 → 胜利或平局动作 → 自动下一局 → 比赛结束。
使用日版 VS MODE 的出厂设定，每局倒计时 60，先赢两局取得该场胜利，默认两边均以持刀霸王丸、怒剑质开局。P1 使用白衣，P2 使用游戏资源内的第二套服装（青色），方便贴身时分辨受击者。双方重叠时依日版战斗逻辑调整绘制顺序，保留跳轻贴身命中的遮挡关系。
可双击 shin.command、zan.command、ten.command、zero.command 或 ken.command，让双方分别以真、斩、天、零或剑剑质开局。若要混合搭配，例如 P1 真、P2 怒，可运行 ./battle.command --p1-spirit shin --p2-spirit rage。命令行和启动脚本使用同一个原生对战程序。
可用 ./battle.command --round-time 0 开启无限时间，也可选 60、90 或 99。时间到按剩余生命判胜，平血双方各得一分。
自动下一局保留胜场、结果历史和原版应保留的槽状态，恢复生命与站位；
双方都差一胜时播放决胜局字幕。整场决出结果后，两名玩家均可使用日版 VS MODE 菜单。
选第二项 CONTINUE 直接再战。P1 用 S 下移、L 确认，P2 用 ↓ 下移、I 确认。手柄可用十字键和 ○。新比赛恢复生命、回合比分和时钟，保留角色、剑质、服装、时间设定和双方的连战成绩。R 重新开始整个试玩会话。
选第一项 CHARACTER SELECT 后左右切到「是」并确认，可重新选人。选人后保留双方的整场战绩。选第三项 RETURN TO TITLE 并确认「是」，会回到已高亮 VS MODE 的模式菜单。P1 或 P2 都可确认，另一席负责下一场的道具和场地。重新进入 VS 后，两人的战绩和服装选择从头开始。
双击 title.command（包内可用 ./run.command --mode title）可直接打开日版标题。P1 按 T、P2 按回车或手柄按 Start 打开模式菜单，向下一次到 VS MODE，然后确认。模式菜单按轻斩或踢退回标题。当前可从这个菜单进入本地双人 VS；街机、练习、调色、选项和标题闲置后的 CPU 排行演示仍在移植。

从选人开始
双击 /Users/xargin/Projects/samsho6-native/select.command。两个玩家分别移动光标并按攻击键确定角色和服色，再分别选剑质。初始光标往下一格是霸王丸。娜可露露在初始位置横移两列、上移两格处，P1 向右移，P2 向左移；等每次翻页结束再走下一列。从 select.command 进入时由 P2 选道具和场地，从标题进入时由确认 VS 的另一席负责，赛后直接重选则由败方负责。默认选「アイテムなし」。想开道具就向右切到「アイテムあり」并确认，场地光标从随机格开始。向右一次到场地 0，再向右一次到场地 1（雪村）。每次等场地图切稳再按下一次，最后确认。对阵介绍中，面键可快进，Start 可跳过。
选人页使用原版全解锁画面：8 列 × 6 行共 48 格，包括 Kim、Rasetsu Galford、紫色娜可露露、Poppy、Shikuru & Mamahaha、Chample 和 PakuPaku，随机格从 47 名人物中抽取；按 Start 切换到黑子页，确认即选黑子（Kuroko）。全部 49 名人物均已接入实战（部分招式与边缘情形仍在移植，见下文）。双方可选同一角色，各自的同伴（鹰、冰精灵、Chample、狼、小狗、人偶、纸牌及环绕物等）分别跟随自己的主人。其余八个可选场地仍在开发，提示出现后可按攻击键重新选人。两页选择、对阵介绍及移门见 character_select_validation.json、character-select-art-validation.json、spirit-select-art-validation.json、versus_faceoff_validation.json 和 vs-curtain-validation.json。进入、重选和再战的窗口回放见 select-session-validation.json。选人进入对阵时，白色渐变的起止和停留已核对；中间亮度目前在合成画面上处理，与 PS2 分别调整色盘和顶点色的做法仍有差异。

场地道具（双人对战）
开启「アイテムあり」后，飞脚会从场边跑入并抛下道具。道具落地后，双方都能走到旁边同时按轻斩＋踢拾取。P1 是 J＋M，P2 是 O＋右方括号，手柄可按 L2。两人同时争抢时，拾取动作完成后才确定归属。
四种食物分别回复 15、3、11、31 点体力，最多回到 200；回血时有原版提示和音效。能扔的道具会在拾取后接上投掷动作。地面炸弹会闪烁并自行爆炸，捡起扔出时引信继续计时；爆炸能伤到扔出它的人。下一局清理场上道具，赛后选 CONTINUE 会沿用道具开关。
道具投送时间和抽选见 stage-item-schedule-validation.json，飞脚和落点见 stage_item_delivery_validation.json。实战拾取回血见 stage-item-contact-validation.json，投掷物和炸弹轨迹见 thrown-stage-items-validation.json。双方投出炸弹，以及场地专属投掷物命中或被格挡的实战对照见 stage-item-bomb-battle-validation.json，实战截图为 stage-item-bomb-hit.png。

服部半藏（服部半蔵）
双击 select.command。从初始光标横移两列、上移一格。P1 按 D、D、W，P2 按 ←、←、↑，每次翻列后松开方向再按。P1 可用 J、P2 可用 O 确认。
以下按面向右输入，换边后左右反转。轻、中、重斩对应 P1 的 J、U、L，踢为 M。
• 近身输入 →、↓、↘＋斩出地面投。跑动中再输入同一指令会使出另一组投技。空中接近跳起的对手，向前＋踢可空投。
• ↓、↙、←＋斩放地面火焰。跳起后 ↓、↘、→＋斩放空中忍术。←、↓、↙＋斩或踢可瞬移。
• 双点前跑、双点后撤。斜跳贴墙后可向场内反跳。近身站重分两段判定；按住重斩不会自动重复出刀。
• 斩剑质满怒持刀时，↓、↘、→＋轻斩和中斩可打落对手武器。在真剑质下，↙、→、↘、↓、↙、←、↘＋中斩和重斩可使出秘奥义。
全部 28 个必杀指令槽的输入在 work/ss6/validate_hanzo_specials.py，命中、格挡与恢复结果见 hanzo-special-validation.json。原生窗口键盘和虚拟手柄对战的 9 秒演示为 hanzo-grab-and-fire.mp4，包含 P1 近身重投和 P2 地面火焰。
专项回放和数据位于 outputs/ss6-feasibility。hanzo_normals_validation.json 核对通常技和移动；hanzo-capture-validation.json 核对配对投技，hanzo-projectile-validation.json 核对忍术物件；hanzo-session-validation.json 与 hanzo-window-input-validation.json 分别覆盖两胜制再战和真实键盘、手柄输入。

真镜名弥娜（真鏡名ミナ，资源 24）
双击 select.command。从初始光标先上移两格，再横移三列（P1 按 W、W 后按 D 三次，P2 按 ↑、↑ 后按 ← 三次），每次翻页结束后再按下一次。
以下按面向右输入，换边后左右对调。轻、中、重斩对应 P1 的 J、U、L，踢为 M，F 对应原版 E。
• 近身直接按斩为近身技。按住前再按斩为弓射：站立前＋轻／中／重斩为站射，斜下前＋斩为蹲射，跳跃中前＋斩为空中弓射。弓射按原版轨迹飞行，部分射角会从站立对手头顶越过。
• 623＋踢：抛出武器后跃向对手上空落下，空中可左右操控，落地后取回武器。
• 421＋轻／中／重斩或踢、623＋斩、41236＋轻／中／重斩：弓箭必杀，含多段箭与天降箭。空中踢和空中 ↓＋斩为空中必杀。
• 重斩＋E、中斩＋E 指挥同伴 Chample 行动，中斩＋E 可让它跳上肩膀。Chample 每局在弥娜身后登场，跟随移动，在主人攻击、挑衅、受击以及登场、胜负时有各自的动作。
• 斩剑质满怒时 236＋轻中可使出武器破坏技：第一箭命中后对手僵直，弥娜接着射出第二箭，命中后打落对手的武器并将其击倒。
蓄力 4〜6＋按键、623＋斩的另一组弓箭必杀和 Chample 的道具相关指令只属于原版的另一种出招模式，普通模式下原版会清除这些指令（14ce28），出厂 VS 设定下不开放。各剑质专属的秘奥义尚未逐项实测；Chample 攻击和跳射回收类的受击演出（原版 B 表第 3、4 行）只在另一种出招模式出现，仍未移植。
资源、绘制、碰撞与声音对照见 mina_resources_validation.json。Chample 的逐帧回调与原版 1fc750 的 1,920 组对照见 chample-validation.json。弓箭的生成与逐帧回调对照见 mina-projectile-validation.json，攻击回调和通用招式脚本解释器的逐访问对照见 mina-special-validation.json。

罗刹丸（羅刹丸，资源 18）
双击 select.command。从初始光标向后翻两列（P1 按 A 两次，P2 按 → 两次），翻页结束后再下移一格（P1 按 S，P2 按 ↓）。
以下按面向右输入，换边后左右对调。轻、中、重斩对应 P1 的 J、U、L，踢为 M。
• 623＋踢；623＋斩；236＋轻／中／重斩（41236 亦可）；236＋踢；214＋踢（自损少量体力并增加怒气，原版脚本事件 28）。
• 236＋轻中、236＋中重为秘奥义类指令，电脑对战中已出现并逐访问对照，公开输入尚未触发。
• 投技命中后由受击方按原版 B 表第 3、4 号两行脚本推进（带等待，原版 165cc0 逐帧处理），包括特效、镜头指令、短暂停顿和震屏。
攻击回调逐访问对照见 fighter_18_special_validation.json，受击方入口 490 组见 victim_rows_18_validation.json，实战受击逐访问见 victim_visits_18_validation.json，资源见 fighter_18_resources_validation.json，缺口探测见 fighter_18_gaps.json。
• 236＋斩放出旋风（描述符 0x2d），命中后把对手卷起再摔落（B 表第 0〜2 号，与霸王丸的旋风同形式）。
旋风的生成与逐帧回调对照见 fighter_18_projectile_validation.json，卷起过程逐帧对照见 whirlwind_victim_18_validation.json。

骸罗（花諷院骸羅，资源 10）
双击 select.command。从初始光标向后翻三列（P1 按 A 三次，P2 按 → 三次），翻页结束后下移一格（P1 按 S，P2 按 ↓）。
• 必杀全部由通用招式脚本驱动；近身投技为原版专用的连打投（1f3cc8 起）：攻击方连按轻、中、重斩和踢凑满一组即加快下一击，打满八组后摔出，撞到身后的画面边缘时震屏。
• 目前限制：电脑操控骸罗时会选用通用普通状态 36（原版 169e00，尚未移植），此时对局按原版行为提示后回到选人；玩家操作不会进入该状态。
攻击回调逐访问对照见 fighter_10_special_validation.json，受击方（含连打投各阶段）见 victim_rows_10_validation.json 与 victim_visits_10_validation.json，资源见 fighter_10_resources_validation.json。

王虎（ワンフー，资源 38）
双击 select.command。从初始光标向前翻一列（P1 按 D 一次，P2 按 ← 一次），翻页结束后下移一格（P1 按 S，P2 按 ↓）。
• 必杀由通用招式脚本驱动；投掷武器的必杀（原版描述符 0x8b..0x8e，第 9〜11 组）会让王虎变为空手，武器落地后成为普通掉落武器，走过去按原版操作捡回。
• 投技命中后受击方按原版 B 表第 0 号四行脚本推进，包括地面冲击效果（世界效果 29）、脚本伤害，以及王虎接着自动发动的追击（结束操作 27 → 他自己的脚本 64）。
• 部分招式持续时会按原版自损少量体力并增加怒气（行类型 0x32）。
对照：飞行道具 fighter_38_projectile_validation.json（生成 114 次、逐帧 9,123 次），攻击回调 fighter_38_special_validation.json，受击 victim_rows_38_validation.json 与 victim_visits_38_validation.json，资源 fighter_38_resources_validation.json。

安德鲁（アンドリュー，资源 30）
双击 select.command。初始光标上移一格（P1 按 W，P2 按 ↑）。
• 必杀由通用招式脚本驱动；射击类招式消耗弹数，命中特定投技会补充弹数，弹数以头顶图标显示（原版 16ea00/16ec48）。
• 扔出的道具在 78 范围内会被自动接回（行类型 0x24）。
• 投技命中后受击方按原版 B 表多行脚本推进，落地阶段使用通用的 174158 回调。
对照：攻击回调 fighter_30_special_validation.json，飞行道具 fighter_30_projectile_validation.json，受击 victim_rows_30_validation.json 与 victim_visits_30_validation.json，资源 fighter_30_resources_validation.json。弹数图标尚未与原版逐帧对照。

橘右京（资源 6）
双击 select.command。从初始光标向前翻两列（P1 按 D 两次，P2 按 ← 两次），翻页结束后下移一格（P1 按 S，P2 按 ↓）。
• 必杀由通用招式脚本驱动；另有一招不经脚本、由原版专用例程处理（选择号 12：先出 ACT 0x246，命中后接 ACT 0x247）。
对照：攻击回调 fighter_06_special_validation.json（含专用例程 1,500 余次），受击 victim_rows_06_validation.json 与 victim_visits_06_validation.json，资源 fighter_06_resources_validation.json。

破沙羅（资源 8）
双击 select.command。向后翻3列（P1 按 A 3 次，P2 按 → 3 次），翻页结束后上移1格（P1 按 W，P2 按 ↑）。
• 选择号 6：留下影子（16c4e0，任务为空函数 1f2c68），本体在计时器 23 期间按摇杆方向以 ±30 移动，结束时挂起影子并以 174158 落地；选择号 2：跃起，接触后按摇杆方向接跳跃。
• 飞行道具组 8（回旋返回的武器 16f088，按接住 ACT 查 4e87d8 目标偏移）、组 15（先漂移后追踪的 16f510，命中时三段爆发）、脚本生成模式 4（16d0e0 及其后续对象 16d1a0/16d270）、脚本结束码 7–13、入口事件 18/19、受击行类型 0x24/0x26 均为本次随之移植的通用机制。
对照：fighter_08_special_validation.json、fighter_08_projectile_validation.json、victim_rows_08_validation.json、victim_visits_08_validation.json、fighter_08_resources_validation.json。

柳生十兵衛（资源 12）
双击 select.command。向前翻3列（P1 按 D 3 次，P2 按 ← 3 次），翻页结束后下移1格（P1 按 S，P2 按 ↓）。
• 选择号 0–2 的必杀不经脚本：按力度查原版 ACT 表（58b3e0 起 6 张表），被打中或命中（本体 104&0xc0000）时转入第二段并以落地收尾。当身架势（攻击状态 73–75）可接住对手（空中/地面各有条件），对手进入受击状态 96–98；状态 79 只记录弹刀。
对照：攻击回调 fighter_12_special_validation.json，飞行道具 fighter_12_projectile_validation.json，受击 victim_rows_12_validation.json 与 victim_visits_12_validation.json，资源 fighter_12_resources_validation.json。

斬紅郎（资源 13）
双击 select.command。向后翻1列（P1 按 A 1 次，P2 按 → 1 次），翻页结束后下移1格（P1 按 S，P2 按 ↓）。
• 选择号 4 是蓄力技：按住的按键决定计时器 22 的累加，达到 0x3c00/0x7800/0xb400 依次升级（ACT 0x241/0x242/0x245），松手即放出。当身状态 73 只接地面攻击。他的重击常造成倒地类型 2（伤害状态 68）。
对照：攻击回调 fighter_13_special_validation.json，飞行道具 fighter_13_projectile_validation.json，受击 victim_rows_13_validation.json 与 victim_visits_13_validation.json，资源 fighter_13_resources_validation.json。

シャルロット（资源 14）
双击 select.command。向前翻3列（P1 按 D 3 次，P2 按 ← 3 次），翻页结束后下移2格（P1 按 S，P2 按 ↓）。
• 选择号 10–12 为蓄力射击：保持期间松开对应按键或动作结束即发射（1f5860 飞行道具，命中或被击时转 ACT 0x21a）。
对照：攻击回调 fighter_14_special_validation.json，飞行道具 fighter_14_projectile_validation.json，受击 victim_rows_14_validation.json 与 victim_visits_14_validation.json，资源 fighter_14_resources_validation.json。

徳川慶寅（资源 22）
双击 select.command。初始光标即是。
• 选择号 7–9 为三段连斩（ACT 0x22c/0x22f/0x232 起，按力度偏移），第三段首次命中时生成接触特效。脚本行类型 0x1e 的接触特效同样移植。
对照：攻击回调 fighter_22_special_validation.json，飞行道具 fighter_22_projectile_validation.json，受击 victim_rows_22_validation.json 与 victim_visits_22_validation.json，资源 fighter_22_resources_validation.json。

雲飛（资源 23）
双击 select.command。向前翻3列（P1 按 D 3 次，P2 按 ← 3 次），翻页结束后上移1格（P1 按 W，P2 按 ↑）。
• 选择号 4 直接抓取（对手当场进入受击状态 96，与空中投相同的立即状态进入）；0x18 为下落攻击，命中时弹起并按摇杆方向选择跳跃；0x1a 为下落特效技。处于 23c&0x100000 时脚本行 8–11 强制转向。
对照：攻击回调 fighter_23_special_validation.json，飞行道具 fighter_23_projectile_validation.json，受击 victim_rows_23_validation.json 与 victim_visits_23_validation.json，资源 fighter_23_resources_validation.json。

腐れ外道（资源 25）
双击 select.command。向前翻3列（P1 按 D 3 次，P2 按 ← 3 次）。
• 选择号 3/4 由 1fe1b8 生成飞行物；描述符飞行道具 0x32 带投技类别，命中玩家时由 1566e8 把对手交给腐れ外道的受击脚本（该对象成为受害方子对象，含接管、子对象等待与结束操作）。前冲为单步（168bf8 位 4）。
对照：攻击回调 fighter_25_special_validation.json，飞行道具 fighter_25_projectile_validation.json，受击 victim_rows_25_validation.json 与 victim_visits_25_validation.json，资源 fighter_25_resources_validation.json。

夢路（资源 28）
双击 select.command。向后翻2列（P1 按 A 2 次，P2 按 → 2 次）。
• 选择号 9/10 不经脚本：保持期间按键（特征 6/7）决定后续 ACT。
对照：攻击回调 fighter_28_special_validation.json，飞行道具 fighter_28_projectile_validation.json，受击 victim_rows_28_validation.json 与 victim_visits_28_validation.json，资源 fighter_28_resources_validation.json。

我旺（兇國日輪守我旺，资源 26）
双击 select.command。从初始光标向后翻一列（P1 按 A 一次，P2 按 → 一次），翻页结束后再下移两格（P1 按 S、S，P2 按 ↓、↓）。
以下按面向右输入，换边后左右对调。轻、中、重斩对应 P1 的 J、U、L，踢为 M。
• 214＋踢；623＋轻／中／重斩；236＋轻／中／重斩；63214＋轻／中／重斩。
• 236＋轻斩命中后接 236＋中斩，再命中后接 236＋重斩，为原版按命中条件（305/306）派生的三段连续技。
• 贴近对手 623＋踢为投技，由受击方按原版 B 表第 0 行与我旺一起播放投出动作。
• 236＋轻中（怒剑质以外、怒气状态）与 236＋中重（真、剑剑质）为秘奥义类指令，尚未用公开输入实测。
我旺的招式全部由通用招式脚本解释器 163610 驱动，没有角色专属回调。攻击回调的逐访问对照见 fighter_26_special_validation.json（双席公开输入及与全部已接入角色的电脑对战，共约两万次访问），受击方 1fe368 的 490 组入口对照见 victim_rows_26_validation.json，资源、绘制、碰撞与声音见 fighter_26_resources_validation.json，全部可输入指令与电脑对战的缺口探测见 fighter_26_gaps.json。

地震（アースクエイク，资源 36）
双击 select.command。从初始光标向前翻一列（P1 按 D 一次，P2 按 ← 一次），翻页结束后再下移两格（P1 按 S、S，P2 按 ↓、↓）。
以下按面向右输入，换边后左右对调。轻、中、重斩对应 P1 的 J、U、L，踢为 M。
• 214＋轻／中／重斩；236＋轻／中／重斩；623＋踢；跳跃中 ↓＋轻／中／重斩。
• 6321＋轻斩＋踢：跳到对手上方后落下（原版脚本事件 47）。
• 236＋轻中（怒气状态）可在空中按前后操控漂移（脚本行类型 5）；目前只在电脑对战中出现过，已逐访问对照。236＋中重尚未实测。
• 挑衅（后＋E）播放 ACT 150，最后一帧以完成码 0 结束；这一结束方式按 120c78 接受，尚未单独对照原版。
攻击回调的逐访问对照见 fighter_36_special_validation.json，受击方 205e40 的 490 组入口对照（含镜头指令队列）见 victim_rows_36_validation.json，资源、绘制、碰撞与声音见 fighter_36_resources_validation.json，缺口探测见 fighter_36_gaps.json。

莉姆露露（リムルル）
双击 select.command。默认光标向上并翻一列、再向上并翻一列、最后只翻一列，就到莉姆露露。翻列方向为 P1 向左、P2 向右；也可以先横移三列，再上移两格。等每次翻页结束再继续移动。
J、U、L、M 分别是 P1 的轻斩、中斩、重斩、踢。持刀时斜下前＋中斩会踏起出刀；空手也有自己的动作。她可以原地跳、斜跳、后撤、前跑、蹬墙。冰精灵跟随她的位置和朝向，在残血取得小局或整场胜利时各有专用动作。
以下按面向右输入，换边后左右对调。地面冰招的指令有 ↓↘→＋斩、→↓↘＋斩、←↓↙＋斩、↓↙←＋斩、↓↓＋斩，也可以连续输入 →＋同一斩键。轻、中、重斩各有对应招式。面对跳起的对手可试 ↓↙←＋轻斩。空中接近跳跃顶点时按 ↓＋斩可立起冰台，站定后按 ↗ 可再向前跳。冰技命中后，冻结与解冻碎片由受击者的状态触发。
前＋Start 弃刀，空手后前跑贴近对手，同时按轻斩＋重斩或轻斩＋踢。斩剑质可长按轻斩＋中斩蓄怒，满怒时持刀输入 ↓↘→＋轻斩和中斩可使出武器击飞技。真剑质秘奥义的指令为 →↘↓↙←、→↘↓↙←＋中斩和重斩。双键在最后一个方向同时按下。
资源、通常技与实战回归分别见 rimururu_resources_validation.json、rimururu_normals_validation.json 与 rimururu-session-validation.json。konru-validation.json 核对冰精灵，rimururu-ice-scene-validation.json 核对冰击、冻结和碎冰的画面。两边玩家使用必杀技的出招、格挡、空手与冰台二次跳见 rimururu-special-validation.json。冰技实战录像为 rimururu-ice-hit.mp4。双方选莉姆露露时，跳轻命中站姿的三个受击姿势分别持续 5、2、2 次更新，命中蹲姿时是 9、3、3 次。rimururu-jump-light-slow.gif 先按原速播放，再放大蓝衣 P2 的蹲姿受击过程。

娜可露露
双方均可使用娜可露露的持刀通常技。轻、中、重斩各含站近、站远、蹲近、蹲远、原地跳、斜跳和跑斩，踢有站、前、蹲、前下、跳、跑六种。双方共 54 组选人对战输入，逐次核对 70 次日版命中和对手剩余生命，见 nakoruru_normal_attacks_validation.json。前跑、后撤、墙跳及弃刀也可操作。面向右时依次输入 ←、↓、↙＋轻／中／重斩（421＋斩）。三档对近身站立的霸王丸分别命中一、二、三次。换边时左右反转。命中、格挡、挥空和收招使用娜可露露自己的动作与判定，见 nakoruru_combat_validation.json 和 selected-combat-validation.json。真剑质的 421 轻斩派生刺击及 3214623＋中重斩秘奥义也已验证致胜与续战，见 nakoruru_round_finish_validation.json。

以下方向以面向右为准。A、B、C、D 分别是轻斩、中斩、重斩、踢。换边时左右对调。
地面输入 ←↙↓＋斩（412＋A／B／C）或 ↓↘→＋斩（236＋A／B／C），可以分别使出アンヌ ムツベ和レラ ムツベ。三档各有自己的移动、攻击判定和收招。↓↙←＋斩（214＋A／B／C）指挥鹰攻击，持刀和空手均可使出。
↓↙←＋踢（214＋D）抓鹰起飞。悬挂时用方向控制移动，轻、中、重斩各有对应动作；按踢松手，松手方向影响落点。悬挂中还可输入 236＋斩或 214＋斩，或在↗、→、↘三个方向分别同时按中斩和重斩。
地面贴身输入 →↘↓↙←→＋重斩（632146＋C）可使出指令投。双方在空中且距离合适时，向前＋踢可以空投；空中向下＋踢可出下踢。抓住后，两名角色各自播放配对动作，落地后恢复操作。
斩或真剑质满怒持刀时，↓↘→＋轻斩和中斩（236＋AB）可使出武器必杀技。斩剑质打落对方的刀；真剑质打碎武器，裁判稍后补刀。两名玩家的抓投、飞鹰和武器必杀回放分别见 nakoruru_capture_validation.json 和 nakoruru-eagle-attack-validation.json。

使用 ./battle.command --mode fixed-versus 可运行原版的另一条固定对局分支。终局胜者页按胜方翻转霸王丸原画，逐字显示 16 条日文台词之一；同分时走 GAME OVER。固定模式默认无限时间，支持相同的命令行设置。

操作

P1 用 W/A/S/D 移动、跳跃和蹲下，J 轻斩、U 中斩、L 重斩、M 踢。F 对应原版 E，T 对应 Start。
P2 用方向键移动、跳跃和蹲下，O 轻斩、[ 中斩、I 重斩、] 踢。反斜杠键对应原版 E，回车对应 Start。
也可以接一至两个 SDL 手柄。先接入的手柄分配给 P1，第二个给 P2，键盘也可同时使用。十字键移动，□ 轻斩、△ 中斩、○ 重斩、× 踢。R1 对应 E，L1 为轻＋中，R2 为中＋重，L2 为轻＋踢。两个扳机按至半程触发数字输入。两个虚拟手柄已验证映射、阈值、热插拔及实战输入。
按住远离对手的方向防御，下后为蹲防。K 和 P 分别是 P1、P2 的后方向快捷键。
面向对手双点前为跑动，双点后为后撤。跑动中按重斩、跳起后按重斩、蹲下时按重斩，均走原版输入选择。
持刀时，站重和蹲重按当时的距离自动选择近斩或远斩。按住攻击键不会自动连发。
贴身同时按中斩和重斩可前投，按住后方向同时按这两键可后投。P1 同按 U 和 L，P2 同按左方括号键和 I。
双方可以投站立、蹲下或防御中的对手。双方同时出投会弹开，已经跳离地面的对手可以避开。
前＋Start 弃刀，后＋Start 挑衅。空手时走到自己的落刀旁，单按轻斩拾刀。换边后前后方向也要换。
↓↘→＋E 在持刀时使出弹返，在空手时使出白刃取。输入方向按当前朝向。倒地落地前可按 E 或后＋E 受身。
对手倒地时可用下前＋重斩追击。P1 面朝右时同按 S、D、L，扫倒后若已越过对手，则同按 S、A、L。
真剑质（霸王丸）
面向右时，↘＋E 前滚、↙＋E 后滚、↓＋E 伏下、←＋E 下段避。换边时将左右方向对调。
持刀输入 →↘↓↙←→←＋E 变身玩偶，出现与复原时都有白烟。空手时同一串输入会出下段避。
满怒持刀时，↓↘→＋轻斩和中斩（236＋AB）使出武器破坏技「天覇凄煌斬」。打碎对方的刀后，裁判会把替换的刀抛回场中。刀落地后，失刀的一方走到刀旁按轻斩可以拾回。
持刀时，↘←↙↓↘→←↓↙＋中斩和重斩（341236421＋BC）使出「天覇封神斬」。每场比赛限用一次，可在空怒时使用。
数字方向按面向右的小键盘方位读，6 为前、4 为后、2 为下。两招的最后一个方向和两颗斩键同时按。
两招起手时舞台转灰，武器破坏技停顿 64 拍，秘奥义停顿 16 拍，出招者的动作继续。
双方实战出招、格挡、碎刀、补刀与再拾刀见 shin_special_validation.json 和 shin_rearm_validation.json。两侧键盘操作及窗口画面见 shin-window-validation.json，实战截图在 shin-window 目录，特效与原版的画面对照见 shin-scene-validation.json。

斩剑质（霸王丸）
按 E 原地闪避，贴近对手按前＋E 绕到对手身后；跳起后按 E 可在空中挡住对手的跳斩。P1 的 E 是 F，P2 的 E 是反斜杠。
按住轻斩和中斩可蓄怒。P1 按住 J＋U，P2 按住 O＋左方括号。中途松开会收招，主动蓄满的一拍有音效和纵向震屏。剩余生命为 1 到 20 点时可以一直保持满怒，下一局恢复满血时清空普通怒槽。
满怒持刀时，输入 ↓↘→＋轻斩和中斩（236＋AB）使用武器击飞技。若刚蓄满，请先松开两键，再随最后的方向同时按下。对手的整把刀会落在场上，失刀者走去按轻斩即可拾回。
怒、真、斩、天、零、剑可以混搭，例如 ./battle.command --p1-spirit zan --p2-spirit shin。手柄 R1 对应 E，L1 或同时按 □＋△ 都可蓄怒和输入武器击飞技。
zan-weapon-hit.mp4 是蓄满、击飞到刀落地的原速有声对战录像；空防与蓄怒的图片在 zan-window。上述文件及验收报告位于 outputs/ss6-feasibility。双方键盘与再战见 zan-window-validation.json，SDL 虚拟手柄见 zan_gamepads_validation.json。人物、伤害和飞刀分别见 zan_actions_validation.json、zan-meter-validation.json、zan_weapon_flip_validation.json。

天剑质（霸王丸）
持刀同时按轻斩和中斩（AB）使出连斩起手。起手命中后，可依次按 AAA、BBC、CCD 或 AABBCCC。每一下分别按、松；同按两个后续键会错过分支。BBC 的最后一下能取消接必杀技，七键长链的末击命中会加怒。
P1 的 A、B、C、D 分别是 J、U、L、M。例如连斩第一路按 J＋U 起手，命中后分三次按 J。E 原地闪避，贴身前＋E 绕到背后。
持刀同按轻、中、重斩（ABC，P1 为 J＋U＋L）可发动怒爆，震开身边对手。剩余生命越少，可用的爆发时间越长。怒爆期间再同按 ABC 出一闪；用过怒爆的剑质槽在本场后续回合保持耗尽，再战后恢复。
天剑质受到攻击会蓄怒。满怒或怒爆中，持刀输入 ↓↘→＋AB 可使出武器击飞技。怒爆或爆发持续期间，原版时钟停在当前数字，变为红色。一闪命中后有白底黑色剪影、命中特效和音乐停顿，格挡或跳开会避开这段演出。
原速实战录像见 outputs/ss6-feasibility/ten-issen.mp4。该目录下的 ten-window-validation.json 核对双方键盘、虚拟手柄及实战画面。ten_chain_validation.json 核对连斩分支，ten_explosion_validation.json 核对命中、格挡及脱身，ten_issen_finish_validation.json 核对一闪致胜与跨局。

零剑质（霸王丸）

双方使用零可双击 zero.command。方向均以角色面向为准。E 配合前、前下、后下、下、后，依次为飞入、前滚、后滚、伏身、避下段。P1 默认 E 键位是 F。
有怒且未满时，按住轻斩＋中斩（P1 为 J＋U）瞑想，将怒气转为无之境地的储备。对手只差一胜、自己的体力降至储备范围时，生命条上的提示开始闪烁。持刀同按踢＋E（P1 为 M＋F）发动「无之境地」，开场光束退去后对手以四分之一速度行动。
境地期间自己被击中或被投会立刻恢复正常速度，成功格挡可维持境地。境地中同按轻＋中＋重斩（P1 为 J＋U＋L）出一闪。对手可以格挡或跳开。命中有停乐、白底剪影和收刀演出。零也有怒爆和武器击飞技。零的一闪需要先发动无之境地。
零剑质原速实战见 outputs/ss6-feasibility/zero-issen.mp4。该目录下 zero-window-validation.json 核对双方键盘、手柄与实战画面，zero_actions_validation.json 和 zero_specials_validation.json 核对回避、瞑想、无之境地和一闪。

剑剑质（霸王丸）

双击 ken.command 直接以双方剑剑质开局。P1 面向右时，F 发动站立见切，S＋F 伏身，A＋F 或 D＋F 避下段。换边后前后方向随角色翻转。成功让对手打到残像会增加生命条旁的秘奥义储量，双方生命保持原值，画面闪白三帧。储量增幅随攻击而变。
下方槽达到 40 点后，轻斩＋中斩（P1 为 J＋U）发动完全防御，消耗 40 点。它能挡住打击与飞行道具，普通投仍然有效。攻击命中、对手格挡或使出必杀可积累下方槽；满槽时输入 ↓↘→＋轻中斩可将对手的武器击飞。
生命降到秘奥义储量以内时，输入 ↓↘→＋中重斩（P1 面向右为 S、S＋D、D＋U＋L）可出霸王丸的天霸封神斩。每局储量从 32 点开始，见切成功可以提高可发动的生命门槛。收式后储量清零，等待 150 次计量更新后开始回充。
见切接天霸封神斩的实战录像在 outputs/ss6-feasibility/ken-mikiri-secret.mp4。该目录下 ken-mikiri-validation.json、ken_defense_validation.json、ken_specials_validation.json 记录日版判定和角色对照，ken-window-validation.json 记录实战画面对照。

R 重新比赛，Space 暂停，N 单步，H 显示判定框，Esc 退出。

当前原生对战

battle.command 进入 versus。两个玩家共享原版规则的输入采样、角色状态机、动作时钟、碰撞与回合调度。
实战窗口绘制日版场地 0 的天空、建筑、马车、人物和地面。两人拉开时镜头缩远，跳起时镜头抬高，不同距离的景物各自投影。七个活动景物有独立的动画时钟。裁判会跟随交手位置、举旗并在刀被打碎后抛回新刀。KO 慢放、赛后菜单和 CONTINUE 再战均保留日版的推进或冻结时机。在 select.command 中可改选场地 1。雪村的房屋、树木、积雪地面和十处活动景物随实战时钟、镜头及调色效果更新。再战或换场后回到雪村，景物从上次离开时继续。
场地 0、1 的原版绘制对照分别见 combat-stage-validation.json 和 combat_stage01_validation.json。场地 2 至 11 的景物任务也已移植，逐访问对照原盘任务的完整提交带和抽样像素，见 combat_stageNN_validation.json 与 docs/combat-stages.txt。./battle.command --stage N 可直接指定场地 0 至 11；10、11 不在选人界面里，没有道具表，音乐未确定，保持静音。雪村的实战窗口见 combat-stage01-duel.png，双方拾取、投出 11 号道具并命中或被挡的实战记录见 combat-stage01-session-validation.json。combat_stage_state_validation.json 记录从正常对战到 KO、菜单、再战的原程序时钟对照。combat-stage00-jump.png 和 combat-stage00-center.png 是试玩窗口截图。
身位、判定框与当时的动作数据决定伤害、受击停顿、退行、格挡、倒地和空中受击。
普通重斩的命中、格挡和交刀会从游戏资源生成各自的特效。双人画面使用实际角色图块、调色板与原队列顺序。
霸王丸持刀时，轻、中、重斩各有站近、站远、蹲近、蹲远、原地跳、斜跳和跑斩。踢有站踢、前踢、蹲踢、前下踢、跳踢和跑踢。
前下踢和跑踢命中会扫倒对手。双方共 54 条普通攻击用例从开局实际输入到受击恢复，见 normal_attack_match_validation.json。
下前＋中斩是独立的中段特殊技，P1 面向右时同按 S、D、U。对手可站防，蹲防会中招。普通下＋中斩依距离打出近或远蹲中斩，见 directional_slash_validation.json。
跳轻命中满血站立霸王丸，生命由 200 降至 191，连续播放三个受击姿势（各 5、2、3 次更新）。在对照样例中，命中后第 10 次更新可移动或防御，第 11 次可出轻斩。蹲姿受击后分别为第 16、17 次。
受击与还手时机见 jump_light_stun_validation.json，站姿、蹲姿（3 个姿势依次持续 9、3、4 次更新）、格挡与空中受击的实际画面见 jump_light_presentation_validation.json。fighter_depth_validation.json 单独核对日版绘制深度和双方贴身时的前后顺序。jump-light-slow.gif 与 jump-light-crouch-slow.gif 分别录下白衣 P1 跳轻命中站立、蹲下的青衣 P2。两段都先以原速播放，再以四分之一速度重放，保留血条和命中火花。jump-light-p2-poses.png 将实战绘制队列中的青衣 P2 单独取出，便于辨认每个受击姿势。
双方均选娜可露露时，蹲稳挨跳轻会从 200 降至 191。前两个受击姿势各持续 9、3 次更新，最后 3 次更新使用与平时蹲姿完全相同的人物图块，此时仍有硬直。双方换边、混合选人及实际画面对照见 selected-jump-light-validation.json。
超斩（原地轻斩＋中斩，P1 的 J＋U）命中可击倒，站防和蹲防都可挡住。专属命中和格挡停顿见 combined_slash_validation.json。
可用必杀指令有 236＋轻/中/重斩、236＋踢（佯攻）、623＋轻/中/重斩、跑动中 623＋轻/中/重斩、421＋轻/中/重斩、214＋踢（酒攻击，用酒壶弹回旋风）和 632146＋轻斩＋中斩（斩钢闪，命中后对手会撞墙）。数字按小键盘方位记，6 为前，4 为后，2 为下。
双方的前后投、投技落空和同时出投见 ground_throw_match_validation.json。跑动弧月斩的三种强度见 running_rising_validation.json。
酒壶的命中、格挡和反弹见 haohmaru_flask_validation.json；撞墙、弹回和受身见 haohmaru_wall_slash_validation.json。武器弃拾、弹返与白刃取已接入双方对战。对手的踢击可穿过弹返。barehand-catch.gif 录下空手接刀及对手掉刀的过程。其余剑质的专属攻击、角色招式和角色仍待完成。
镜头按日版动作记录震动。霸王丸的 421＋轻、中、重斩各触发一次纵向震动。632146＋轻中斩连续触发四次。两类招式挥空也会震。236＋斩的旋风命中时，由卷起的对手触发两次。普通重斩没有这项镜头指令。触发条件和时钟见 shake-input-validation.json。camera-shake-special.gif 录下斩钢闪的原速实战，camera-shake-scene-validation.json 核对命中和挥空时的镜头与画面。
空手时可站、蹲、原地跳、前后跳、跑动出拳或踢击。原版会让多个强度共用动作。unarmed_normals_validation.json 覆盖双方共 80 组输入，含命中和挥空。
倒地追击有持刀和空手两种动作，pursuit_attack_validation.json 核对命中、错过倒地窗口以及追击致胜后的自动续局。
画面上方显示双方头像、生命条、剑气、胜局标记与倒计时。生命条在每次碰撞结算前读取体力，所以跳轻打中时先出现受击动作，下一次更新才缩短黄条。红色损血段在持续受击时保留，食物回血按每次更新一点显示。六种剑质使用各自的生命条提示。对应的实战窗口与状态核对见 battle-life-hud-window-validation.json、life-food-window-validation.json 和 life-hud-state-validation.json。

画面下方分别显示两位玩家的怒槽。怒剑质受击积怒，挡普通攻击不积怒，挡特定必杀也能积怒。满怒后槽标闪动，攻击增强。实战对满血霸王丸的近身重斩从 38 伤害升为 57。怒气消耗受受击和回合状态影响，下一局按原规则继承余量。怒气与倍率对应 versus_rage_validation.json、rage_attack_match_validation.json，画面对应 live_rage_hud_validation.json。
fixed-versus 的平局结算会播放霸王丸倒地的三个原版姿势与「これにて終了 / GAME OVER」字样。场地沿用上一场的七个动画时钟，切到固定镜头。人物和场地按游戏结算色盘转成灰阶，按键快进只跳过结算文字演出，场景动画按原速继续。胜者页与平局页的停留、跳过和幕切换时机已核对。渐变期间的颜色目前由 SDL 在最终画面上混合，原版还分别处理各色盘，过渡中的部分像素仍有差异。
试玩直接播放日版光盘中的挥刀、命中、格挡、交刀、霸王丸喊声与相应必杀音效。声音经过原声道分配、音量和音高规则混合，由 SDL 输出。跳轻打中和被挡有各自的声音，jump-light-hit.mp4 是当前双人窗口的原速有声录像。首局、第二局、决胜局及 KO、时间到等结束字幕会播放对应的日语报幕。场地 0 使用原盘 BGM05，雪村使用 BGM06。各自的左右声轨在第一局开打时进入，普通 KO 及下一局沿用同一段音乐。整场胜负确定后转为胜利曲，赛后菜单有移动、确认和取消音。
可用 ./battle.command --match-replay 回放文件 --audio-out 对战.wav 离线录制同一段对战的 48 kHz 双声道声音。每次对战更新输出 800 对采样。实际输入与录音核对见 live-combat-audio-validation.json。音库与驱动见 combat-sound-bank-validation.json、combat_audio_validation.json。combat_music_validation.json 核对双声道与循环，round-opening-sound-validation.json 核对报幕时机，stage_music_events_validation.json 核对从首局、决胜到菜单和再战的换曲。窗口卡顿后会清理设备队列里积压过久的旧音，录制的 WAV 保留所有采样。音乐按本地资源就绪时的驱动时序播放，实机读盘寻道带来的额外延迟尚未实测。验证采用日版程序、光盘数据和独立混音对照，尚未取得实机的逐采样录音。
历史脚本试验可用显式 --mode trial 调用。

验收记录位于 outputs/ss6-feasibility。versus_heavy_validation.json 含98组实际键盘输入和两场从满血开始的比赛，覆盖双方重斩、地面投、冲刺623、轻中同按、下前中斩、214踢、632146轻中，以及跳轻受击后最早还手的时机。新增样例包含挑衅、弃刀、拾刀、两种受身、弹返、白刃取、倒地追击，以及空手站中、蹲踢、跳轻、跑重的实际命中。
console-versus-session-validation.json、console_versus_menu_validation.json 与 console_versus_art_validation.json 分别核对原版再战初始化、选择流程和菜单画面。live_console_versus_validation.json 核对打包窗口和两场连续实战。
versus_gamepads_validation.json 记录 16 个手柄实战用例。versus_result_validation.json、versus-result-art-validation.json 和 versus_result_text_validation.json 分别记录赛后状态、原画与台词核对。live_winner_validation.json 用双方实际赢下的比赛核对最终窗口。versus-draw-stage-validation.json、versus_draw_art_validation.json 和 live_draw_validation.json 对照 GAME OVER 的场地、人物、标题和最终窗口。
weapon_handling_validation.json 与 weapon_pickup_validation.json 核对弃刀、落刀、拾刀距离和动作恢复。weapon_deflection_validation.json 和 weapon_deflection_effect_validation.json 核对双方的兵器反应和画面特效。
jump_motion_validation.json 记录54条空中动作轨迹的原程序对照。dash_motion_validation.json 记录36条冲刺和后撤轨迹。
air_hit_validation.json 和 heavy_weapon_contact_validation.json 分别覆盖空中受击、双重斩相遇及倒地受身。
native_scene_validation.json 核对从队列到角色图块的合成。原版主机的整帧显示和整款游戏的全部机制仍待验证。

此前试玩构建的验证记录
- 霸王丸的站立与蹲下轻重斩共用原版输入优先级，按键顺序不会改变同拍结果。
  H 显示实际攻击区域，重斩与轻斩的攻击框均为红色。该历史试玩包 SHA256 为
  f75ad83acb0ee1234c8ba736eef10d27ebacf69cde932a1c3d0dfc704068e154。
  原版按键与选择对照见 slash_input_validation.json，SDL 键盘事件对照见 sdl_slash_input_validation.json。
  两份报告均位于 outputs/ss6-feasibility。
- 站重和蹲重各从满血完成 2:0、0:2、2:1 三种比赛，自动续局、终局和 R 重赛均可运行。
- 独立角色渲染器现已核对贴图排列、阴影、刀光、透明色和调色板，详见 docs/character-draws.txt。

此前开发记录（构建指纹对应各自的验证日期）
- 已补普通对象的绘制准备：掉刀、拼刀公共对象及选定角色动作保留原阴影、翻转、颜色和图层规则。
  10,163场景/24,628贴图提交通过原程序对照，含7,348阴影；修正加亮绘制后恢复混合模式的边界。
  这是最终图块/调色板绘制前的数据，尚未替换试玩画面；详见docs/character-draws.txt。
- 粒子、字幕、拼刀公共对象和普通落刀已共用原版511项绘制队列，保留绘制后再推进/释放的时机。
  24条自然轨迹35,404快照、混合容量/排序/释放3,350快照通过；旧粒子9,908及开场quick4,837回归通过。
  相同深度保持提交顺序，队列满仍正常更新和回收。尚未接入可玩拼刀或完整硬件主循环。
  本轮未换试玩包，当前重攻击操作不变；详见docs/unified-draws.txt。
- 公共特效与普通落刀对象的动画、运动、回调回收和原始绘制队列已实现并组合核对。
  对象阶段4,324快照、24条角色到落刀轨迹35,404快照通过；双方在三种速度下均按原时机落地。
  归属者颜色/运动、暂停、记录跳转、511项绘制容量和保留字段均有原程序对照。
  尚未切入可玩拼刀或完整主循环，特殊落刀仍待继续；共享队列进展见上项。详见docs/auxiliary-frames.txt。
- 拼刀角色胜负回调与真实掉刀已独立接入状态机：胜者收招，败者在原动作保持点掉刀并恢复无刀待机。
  24条连续轨迹、6,988快照与15,049粒子绘制快照通过，含双方获胜、平局、超时和场边位置。
  掉刀入口另按原位置表核对918场景；共享控制器4,964及原地面输入quick子集1,716快照回归通过。
  公共对象和普通掉刀阶段已在本次新增组合验证；实战触发仍待接入，当前试玩包尚不能操作拼刀。
  本轮未换包；现有重斩完整比赛回归通过当前构建，详见docs/weapon-lock-actors.txt。
- 拼刀动作137..140的原记录播放与粒子命令已独立接通；原版随机速度、偏移、镜像、深度与暂停释放均保留。
  动作到粒子32,760快照、共享粒子生命周期9,908快照、全部已支持效果1,640个投影场景通过。
  角色对象133,832、开场4,837、结束入口8,206快照及重斩整场比赛回归通过。
  normal31胜负回调、实际掉刀及对象阶段已另行组合，完整主循环仍待接入；尚未将拼刀切入可玩样例。
  当前构建的重斩报告与此前打包窗口证据分别保留各自指纹；详见docs/weapon-lock-actions.txt。
- 已重新验证并更新当前重攻击试玩包：站立近／远重斩、蹲重、格挡、弹刀和倒地恢复均通过。
  站重23场景／12,928随机快照／568像素场景，蹲轻重96场景／12,000原调度投影／948像素场景，
  重追击600个原角色调度投影通过；站重与蹲重分别跑完2:0、0:2、2:1自然比赛。
  当前包43个SDL窗口检查及从项目外启动battle.command通过。试玩仍为霸王丸持刀system0、静音。
  包指纹：c44b4ed89a9a2bb3c59a0a62da4200140d472cc215d1a155f07f70cfa75190c7。
  当前包的窗口证据为heavy_request_smoke_validation.json；组件重构后的构建回归另按报告所载指纹记录。
  完整原版输入、其他角色与跳重不在此可玩范围内。
- 新共享回合分派已组合各阶段，保留进入/更新分离、延迟旧值判断和结束后不重复记胜场。
  2,528个分派快照、144个换局快照、8,206个结束入口快照通过原程序对照。
  活动拼刀控制现另通过4,964快照，使用同一共享对象池；公共对象阶段现已另行组合验证；结果菜单及完整主循环仍待接入。
  拼刀组件尚不可玩；角色回调与掉刀的后续独立组合见本次记录，当前重攻击试玩范围见下方说明。
- 新共享控制已接上本局结束入口：记录双方胜负、选择终局动作、停止气槽、设置原暂停并创建字幕。
  终局选择5,144快照、结束入口8,206快照通过，含16组从结束入口到胜利阶段的组合。
  当前覆盖普通本地对战、静音且禁用档案记录；组件仍待并入完整主循环，试玩包未替换。
- 新共享控制已补齐开打、普通KO/时间结束判定、双方气槽任务，以及结束字幕到胜利阶段的等待。
  气槽3,429、战斗控制2,480、结束字幕6,605、结束控制15,836个原程序对照快照通过。
  保留原版暂停、怒气到期、待提交动作与字幕释放的先后顺序；这些组件尚未切换到当前试玩包。
  重斩23场景、12,928随机快照、568像素场景和自然完整比赛回归通过。
- 新回合控制已接上开场字幕的共享任务、完成回调和输入解锁请求，9,983个原程序对照快照通过。
  包含全部回合字幕的暂停/恢复、连续六次开场，以及与角色对象共用任务池后的释放与回收。
  这部分尚未替换试玩包的现有控制；重攻击仍可直接用上方列出的按键试玩。
- 新对战组件已串起双方换局、场边事件和开场进入，连续48次换局/144个快照通过。
  开场/胜利进入的事件优先级、位置边界、随机数副作用另有1,515个对照快照通过。
  这些仍是组件整合进展，当前试玩包与重攻击操作保持上一轮验证版本。
- 重攻击试玩包已更新，修正KO镜头误加等待的问题：原版检查败者是否存活，普通KO直接移向胜者。
  站立/蹲下重斩双方2:0、2:1比赛与43个实际SDL窗口检查通过；仍是霸王丸持刀system0样例。
  新回合控制的6个原函数通过1,108个对照快照，其余阶段尚未接到当前可玩控制。
- 普通外层换局已接到双方共享状态：按原版次序清理对象、初始化双方并回收任务。
  48次完整外层换局、144个快照通过，包含双方持续输入记录、怒气、随机数和旧动作历史；
  另有96次连续对象分配/回收检查。完整原版回合控制器与主循环仍在整合。
- 持续角色组件已补齐换局初始化，沿用同一份角色、输入、随机数和对象池。
  32组场景、64次完整原函数、9,296个状态快照通过，包含换局后继续出重斩。
  修正新动作提交前的旧身体标志和历史；补上重斩声音选择对随机数的影响。
  这些是独立组件进展；当前可玩包仍用已有对战控制，音频仍静音。
- 原版持续输入到地面姿态的独立执行链已接通，包括蹲起、转身、方向防御的进入/退出。
  8,800组合快照与原角色调度的指定字段一致，新输入组合入口也通过原5,344项生命周期回归。
  现已补上站立/蹲下的轻重斩回调及输入前的状态门控、攻击窗口计时，持续保留指令进度。
  新增6,712攻击输入快照通过原程序对照，覆盖双方、近远、朝向、按住/连按及收招输入。
  现又接入普通受击、格挡、弹刀及原版命中停顿回调，14,972个连续状态快照通过对照，
  包含重斩被打断和收招间隙再中招；保留跨受击状态的追击记录，修正格挡漏设的计时器。
  重斩倒地、两次落地、普通起身也已接入该链，新增8,668个状态对照通过，
  包含倒地中按键及起身间隙再受击；受身方向目前仅验证请求边界，翻滚动作尚未接入。
  致命受击改选、KO落地与结束保持也已接入，72条轨迹/8,025个快照通过；
  输入锁定时仍执行原版恢复检查，保留普通倒地死亡后的保持行为。
  登场、胜者等待、胜利/终局和败者倒地也已接入，52个场景/10,704个快照通过；
  包含释放登场后实际出重斩，以及KO转败者倒地后持续输入仍保持结束状态。
  补齐原版怒气/颜色/透明度更新，15,038个整函数检查通过；动作队列归各角色持有，
  按原版分别执行角色回调、动作请求提交和身体动作切换，保留换局历史采样的时机。
  16条颜色与输入组合轨迹、4,656个快照通过，覆盖双方、双朝向和怒气状态0..3下的站蹲重斩。
  这部分尚未切换到当前对战控制；详见docs/ground-input-execution.txt。
- 接入蹲下、蹲轻191/192、蹲重195/196，以及原版收招回到蹲姿的时序；保留近远阈值78。
  蹲重使用自身判定/伤害描述，站防和蹲防规则不按姿态臆测。收招待机被新受击打断也已验证。
  96类接触场景、12,000个原角色调度投影状态、948个独立像素场景，以及双方2:0/2:1自然比赛通过。
- 补齐重受击期间再次被重斩命中的击倒分支：384腾空与两次落地、尘土、48倒地、52起身，
  最后恢复操作；致命追击能进入KO和自动下一局。两方向、近/远均验证。
  84条原回调轨迹/57,221状态、600次完整角色调度的指定字段对照、402个新增像素场景通过。
- 接入霸王丸站立重斩：自动近身189/远身190、完整动作和刀光、命中与格挡、强度2剑气消耗、
  重受击停顿/恢复及独立弹刀143。P1按L，P2按I。近/远全部30个动作阶段完成像素检查。
- 用重斩从200HP打完双方2:0及2:1比赛，自动换局、怒气保留、终局与重斩双KO通过。
  新增568个独立像素场景、12,928个混合控制快照；原轻斩和整场流程回归通过。
- 掉刀对象所需的任务/对象池、原随机数、kind4/6初始化、普通掉刀和静音落地基础已实现。
  2,632组原函数对照通过；完整受击回调、对象调度和绘制尚未接入可玩对战。
- 补齐强制状态、普通出招、变身及输入受限时的请求调度，30,920组原程序对照通过。
  包括KO/怒气启动、双状态请求通道、自定义系统取消与角色辅助动作请求。
- 补齐人类输入采样门控、变身指令表替换、角色蓄力和输入清理；清缓存保留未完成指令。
  修正取消许可检查中遗漏的计时器递减，所有35个计时器均纳入对照。
- 完整动作进入及主/变身状态切换已原生实现，包括姿态、条件、指令缓存消耗、
  槽状态、效果清理与状态标志更新。24,639组整函数对照通过；原有6,144组前段检查仍通过。
  实际动作回调仍在补全，尚未替换当前对战的直接控制。
- 普通/攻击/变身回调注册、攻击进入时的怒气增长、受击掉刀条件和系统效果退出已移植。
  36,410组整函数对照通过，包含全部角色描述表、共享辅助对象和双方同时激活系统效果的边界。
  回调注册不等于招式已执行；掉刀对象创建已独立实现，完整受击入口、对象调度和各招式回调仍在补全。
- 96个出招权限检查、完整权限过滤流程，以及必杀/取消/受击脱身请求已原生实现。
  96,326组对照通过，覆盖副作用、输入缓存保留、优先级和角色专属分支。
  这些仍是输入库进展，当前可玩对战尚未接入完整必杀和取消流程。
- 普通/攻击/连斩/系统动作选择、转身限制及动作请求已原生实现；防御威胁检查包含
  对手飞行道具与角色辅助状态。122,328组独立原程序对照通过，尚未接入当前对战。
- 原生输入子系统：273条指令模板、方向转换、组合键、蓄力、超时、按键/完成缓存与600次输入重放。
- 48个原始角色编号的指令绑定、system0..8可用性与原版优先级排序已独立核对。
  上述是输入库进展；当前对战仍使用直接状态控制，尚未接上完整动作选择与取消流程。
- 主入口接入首局初始化及双方霸王丸登场，按原回调完成标志进入字幕，不硬编码演出时长。
- 登场动作492的21个阶段、零时长回调放行、武器双向翻转和半透明身体均接入。
- 补齐登场timer34等待/复位/重播分支；当前同角色对战按原版无需错开登场。
- 修正待机动作的怒气选择与进入时机：既有待机不随数值变化重启，再次进入时才重新选择。
- 串起后续回合初始化、开场字幕、输入解锁、胜局累计与终局停止边界。
- 后续回合按原版走 state1→3，跳过首局专用 state2；保留计时器旧值门控。
- 接入持刀决胜动作499/501及KO字幕16，终局暂停60次、普通KO40次，均延后2次开始。
- 补齐499武器纵向翻转、501的bank26刀光；已有运动命令5现在覆盖这些动作。
- 角色历史与三组残影描述状态已验证；本样例的动作均不产生可见残影，渲染路径仍待接。
- 原版149008/13fd80对照执行真实库日志与池分配，没有跳过函数冒充整函数通过。
细节、原始地址和准确证据范围见 docs/crouching-slashes.txt、docs/heavy-knockdown.txt、docs/standing-heavy.txt、docs/auxiliary-objects.txt、
docs/state-callbacks.txt、docs/state-entry.txt、
docs/input-routes.txt、docs/input-lifecycle.txt、
docs/input-permissions.txt、docs/action-selection.txt、docs/input-processing.txt、
docs/character-introduction.txt 和 docs/continuous-match.txt。

早期试玩的范围记录（当前可用操作见本文件开头）
- 只接霸王丸资源00、持刀、system0和列明的普通地面状态；轻/重斩含站立和蹲下的近远动作。
  连续重受击damage64已接普通倒地/起身；跳跃攻击、中斩和受身输入/翻滚尚未接。其他角色、招式、跳跃、
  投技、必杀、系统选择、AI、游戏模式未移植。原版按键缓存已在输入库验证，
  对战尚未接该输入库以及取消、转身、指令消耗和完整动作选择流程。
- 首局已接同角色霸王丸登场；异角色语音错开选择、其他角色辅助对象仍未接。
- 原版菜单、时间到、介绍/胜利演出按键跳过、局内评分事件和比赛结果保存尚未接。
- route7/8的命中/弹刀效果、音效、连击统计等副作用尚未完整接通。
- 普通剑气/怒气槽及待机动作选择已有；怒气颜色脉冲已接入独立角色组件，预览绘制尚未接。
  怒气爆发等玩法仍待接入。
  训练设置与限时条件的待机选择已单独核对，但完整训练/限时模式尚未接入。
- 终局仅集成持刀499/501；空手500有独立动作测试，502含尚未实现的header400，拒绝放行。
- 角色历史已移植，可见残影、完整actor任务调度与全角色辅助对象仍未实现。
- 画面仍是400x160检查裁剪，未接完整舞台背景。角色RGB1555、效果PS2专用CLUT、
  PIL透明/相加/翻转与旋转四边形已显示；GS混合顺序、硬件采样和全局染色仍未核对。
- 声音静音，60Hz是开发预览节奏，未证明等同PS2显示/输入采样相位。
- 伤害、运动与镜头使用显式有限浮点模型；同模型对照不等于EE硬件低位一致。
- 原版完整帧轨迹、实机图像、完整游戏1:1尚未验证。

验证证据（outputs/ss6-feasibility）
battle_round_entry_validation.json：普通state0换局到state1发布，48次完整13fd80/96次149008，
  外层按明确入口片段核对，另有任务回收和动作提交；不宣称完整143430或实战输入已完成。
round_presentation_validation.json：场边事件的完整函数及开场/胜利进入的明确尾段，
  1,515个快照；包含事件排队、位置/朝向、RNG与静音选项下的终局声音等待位。
round_control_validation.json：6个完整原回合函数、1,108次快照；涵盖跳过、提前返回、
  双方请求/计时/身体、KO与存活败方镜头分支。完整控制器和SDL原输入整合仍待完成。
crouch_match_camera_validation.json：镜头修正后的蹲重双方2:0及2:1自然比赛与确定性重放。
battle_round_validation.json：双方共享状态的48次完整13fd80、96次149008、48次112838和144快照；
  原生动作提交阶段分开验证，换局间为边界夹具，不宣称完整比赛帧对照。
task_dispatch_validation.json：1,196次整函数、3,405次真实回调，含96次连续清理/重新分配/调度；
  原协程业务和完整对象阶段仍待接入；kind4/6/7的新增支持见本次记录，3项原生回调接口检查单独标注。
ground_round_input_validation.json：32组/64次完整149008/9,296连续快照，含双方首局及后续局、
  四种怒气状态、两套RNG、实际残影池/历史和保留输入；外层控制器仍是明确边界。
sound_selection_validation.json：3,096次完整声音选择，保留随机数与共享前次声音记录；无音频输出。
state_callbacks_task_pools_validation.json：36,410项真实任务注册表/共享对象池回调对照。
ground_ending_input_validation.json：52场景/10,704连续快照，包含10,220次完整角色回调调度，
  登场释放、等待/胜利/败者保持以及开打后的重斩；回合状态与锁定仍由夹具提供。
actor_color_validation.json：15,038次完整颜色更新，覆盖怒气脉冲、显式颜色、闪光、透明度及整数边界。
ground_color_input_validation.json：16轨迹/4,656连续快照，含4,448次完整角色回调调度，
  额外比较颜色字段与各角色动作衔接；未集成主对战渲染，不是GS图像验证。
actor_action_queue_validation.json：192组/384次完整149918；重复提交与同动作拒绝保留原队列清理行为。
ground_state_validation.json：8,800连续快照，含8,656次完整149d08及3,056次输入请求片段。
ground_input_boundaries_validation.json：独立地面输入组件的方向防御、输入锁、同时方向和转身边界。
ground_attack_input_validation.json：6,712攻击输入快照，含6,584次完整151b00/151eb0/149d08。
ground_damage_input_validation.json：14,972受击/格挡/弹刀输入快照，含14,632次完整149d08；
  5,384次持续输入还组合接触后片段和计时/生命阶段。独立组件，尚未切换实战控制。
ground_downed_input_validation.json：8,668倒地输入快照，含8,468次完整149d08、80次受击请求
  和40次真实落地效果分配；12项受身边界停在请求及状态提交，不宣称翻滚已可玩。
ground_ko_input_validation.json：72条KO输入轨迹、8,025快照、6,504次完整149d08，
  含致命受击改选、倒地/起身间隙死亡、输入锁定和576项超时边界；独立组件，待接主循环。
ground_ko_watchdog_edges_validation.json：40项负数状态哨兵、超时阈值及请求保留的原函数对照。
ordinary_validation.json：近远选择、弹刀请求、挤压及504项原版距离片段对照，含小数坐标边界。
actor_timer_pass_validation.json：1,152项完整151eb0，含旧值门控、停顿分支及辅助对象标志释放。
crouching_trial_validation.json：96类场景、96次完整14c2d0、12,096次完整149d08的12,000投影状态；
  12,928混合控制快照、蹲轻400/蹲重548像素场景，三场自然蹲重比赛4533/4533/6583次更新。
crouching_window_validation.json：当前打包版本的蹲斩/受击/格挡/收招打断/终局实际窗口检查。
heavy_reaction_validation.json：4,224组重击选择（含damage64）及66轨迹/7,260状态的重受击回调对照。
knockdown_validation.json：84条轨迹/57,221状态，含544组受身请求边界；系统8延迟起身仅独立回调验证。
knockdown_trial_validation.json：600次完整149d08的指定字段对照，四种实际追击及四种致命追击续局。
knockdown_image_validation.json：402个独立像素场景，覆盖腾空、两次落地、尘土和完整起身。
heavy_trial_validation.json：12组完整149d08进入指定字段，23类接触/恢复场景，
  12,928随机快照、568独立像素场景、三场自然重斩比赛；不冒充完整原版帧轨迹。
heavy_window_validation.json：当前启动包38个实际macOS重斩/击倒/比赛窗口。
heavy_request_smoke_validation.json：上述38个窗口，加5个蹲重/蹲重比赛窗口，共43个；
  脚本控制，不是物理键盘或PS2画面对照。
packaged_heavy_smoke_validation.json、crouching_window_validation.json及battle_ending_window_validation.json
  保留之前版本的检查记录，具体二进制以各报告指纹为准。
object_pool_validation.json / game_random_validation.json：2,220组对象池及8,020组随机数对照。
auxiliary_objects_validation.json：2,632组辅助对象/掉刀基础检查，尚未接入对战调度。
command_input_validation.json：273条模板、546组成功输入谓词轨迹、19,932个状态快照。
input_features_validation.json：4,154组按键采样/方向/组合键/缓存/重放对照。
input_pipeline_validation.json：512次完整179530，从软件按键状态到全部指令结果。
input_bindings_validation.json：1,040次完整179258，覆盖48个角色编号和9种系统。
input_stream_validation.json：实际绑定加连续软件按键序列，检查出招识别与失败边界。
  这些输入验证均不代表对应角色/招式已能在当前对战中执行。
action_selection_validation.json：71,296组状态表、输入优先级、转身及角色状态别名对照。
attack_request_validation.json：33,792组完整攻击/连斩/附加系统动作请求与拒绝边界。
normal_request_validation.json：17,240组普通动作请求、防御威胁、方向转换对照。
  三项比较状态选择与请求字段；不代表完整动作执行或整场对战输入已通过。
input_permissions_validation.json：45,205组权限回调、对象可用性和指令过滤对照。
permission_stage_validation.json：28,579组状态门控、辅助对象、取消许可和完整权限阶段对照；
  其中4,989组为开方指令尾段检查，浮点模型证据不等于EE实机一致。
special_requests_validation.json：22,542组完整必杀/取消/受击脱身请求对照。
input_routes_validation.json：30,920组请求调度对照，包含1,728组权限→强制→普通请求组合，
  以及2,048组完整受限输入分支；比较全部计时器、双请求通道和缓存清理副作用。
input_lifecycle_validation.json：5,344组完整输入清理/角色蓄力函数和明确标注的1494f0片段；
  包含864组从真实软件按键采样直到出招请求的组合对照，覆盖48个绑定编号和9种系统。
  各片段内真实执行被调用函数，不冒充完整角色更新、动作执行或AI已经完成。
state_entry_validation.json：6,144组状态请求判断、提交及1491e0进入准备；
  此历史前段检查明确停在14a348之前。完整进入由下面的新报告另行验证。
state_transition_validation.json：24,639组整函数对照，包括822次完整14a348、512次1491e0、
  576次变身状态切换、768次状态标志更新，以及全部16,464条描述记录、姿态/条件/效果清理。
  比较全部计时器、指令进度、两类256槽任务池及回收顺序；不代表完整149d08动作回调已完成。
state_callbacks_validation.json：36,410组回调注册、怒气增长、掉刀条件与系统效果退出对照；
  其中1,536组串联原版状态标志更新与攻击注册。33,229组仅整数运算，3,181组显式有限浮点模型。
  完整受击入口和招式回调执行尚未包含，不声称对应招式已能游玩。
match_flow_validation.json：从200HP只用移动/轻斩打完双方2:0与2:1；确定性重放、
  自动换局保留/重置、输入锁、40/60暂停及终局均检查。另5组明确初始条件检查低血/终局双KO，
  非终局双KO另检查90次等待、双方复位与下一局实际命中。
character_intro_validation.json：首局236次更新的指定字段对照，包括472次完整149d08；
  原版登场完成门控、零时长放行及原生开打后的实际命中均检查。
round_entry_validation.json：256组完整149008的已表示字段与原生一致，含首局/续局和rage0..3。
round_flow_validation.json：128组完整13fd80，3,968次完整1435d8，216个字幕选择明确片段。
  比较指定字段；不声称整个143430或完整原版帧通过。
actor_history_validation.json：2,048个历史状态，6,144次完整残影回调对照。
ending_playback_validation.json：120组、194,424个对象状态，含登场492及持刀终局499/501。
idle_choice_validation.json：4,608组完整169d10动作选择与36组待机连续性轨迹；
  连续性通过324次完整149d08和对象回调对照，当前对战接入普通怒气0/1状态。
knockout_image_validation.json：2,213个登场/KO/胜利/字幕画面，2,043个原效果四边形片段；
  独立Python PIL合成与预览一致，不是PS2 GS截图对照。
contact_trial_validation.json：17类集成场景、7,776个随机快照、223个独立像素场景。
每份报告记录其执行范围和二进制指纹；独立函数报告不冒充整游戏验证。

构建与运行
cmake -S . -B work/ss6/build-native -DCMAKE_BUILD_TYPE=Release
cmake --build work/ss6/build-native -j 4
python3 work/ss6/package_viewer.py
./battle.command
当前使用本机已安装的SDL3，尚未制作跨机器独立分发包。
必须用package_viewer.py原子替换可执行文件；本机原地覆盖曾触发macOS可执行缓存SIGKILL。

复现关键检查
python3 work/ss6/validate_battle_round.py --entries
python3 work/ss6/validate_round_control.py --presentation
python3 work/ss6/validate_ground_state.py --ending
python3 work/ss6/validate_ground_state.py --colors
python3 work/ss6/validate_actor_color.py
python3 work/ss6/validate_actor_action_queue.py
python3 work/ss6/validate_ground_state.py --ko
python3 work/ss6/validate_heavy_reactions.py
python3 work/ss6/validate_heavy_trial.py
python3 work/ss6/validate_heavy_windows.py
python3 work/ss6/validate_object_pools.py
python3 work/ss6/validate_game_random.py
python3 work/ss6/validate_auxiliary_objects.py
python3 work/ss6/validate_command_input.py
python3 work/ss6/validate_input_features.py
python3 work/ss6/validate_input_pipeline.py
python3 work/ss6/validate_input_bindings.py
python3 work/ss6/validate_input_stream.py
python3 work/ss6/validate_action_selection.py
python3 work/ss6/validate_attack_requests.py
python3 work/ss6/validate_normal_requests.py
python3 work/ss6/validate_input_permissions.py
python3 work/ss6/validate_permission_stage.py
python3 work/ss6/validate_special_requests.py
python3 work/ss6/validate_input_routes.py
python3 work/ss6/validate_input_lifecycle.py
python3 work/ss6/validate_state_entry.py
python3 work/ss6/validate_state_transition.py
python3 work/ss6/validate_state_callbacks.py
python3 work/ss6/validate_round_entry.py
python3 work/ss6/validate_character_intro.py
python3 work/ss6/validate_idle_choice.py
python3 work/ss6/validate_round_flow.py
python3 work/ss6/validate_match_flow.py
python3 work/ss6/validate_ending_playback.py
python3 work/ss6/validate_actor_history.py
python3 work/ss6/validate_contact_trial.py
python3 work/ss6/validate_knockout_images.py
python3 work/ss6/validate_battle_windows.py
python3 work/ss6/validate_slash_inputs.py
python3 work/ss6/validate_sdl_slash_input.py
python3 work/ss6/validate_heavy_windows.py

其他检查入口
opening.command：独立初始开场字幕样例，不自动续局，R回普通对战样例。
knockout.command：6个原始倒地动作独立预览；--action 400/401/402/403/382/383。
run.command / contact.command：旧动作/双角色候选接触检查器；其标记不代表命中扣血。
旧检查器：1待机、2前进、3后退、4攻击185、G防御快照、C双角色、Tab静态图像。
所有入口支持--snapshot PATH.bmp和--dump PATH.rgba；--updates N推进指定次数。原生 versus 的 --dump 为带场地、角色和特效的 640×448 战斗区；--dump-stage PATH.rgba 可单独导出场地。两种 RGBA 文件均含 8 字节小端宽高，--snapshot 输出含 HUD 的 640×480 窗口图像。
--trial-script PATH选择明确初始场景；脚本life只允许首次tick之前，不能在实战中改血。
work/ss6/scenarios/match-00.txt / match-11.txt / match-010.txt保存完整控制重放。

原始资料与未解问题
镜像SLPS_255.59、NTSC；源ISO保持只读，指纹见iso_manifest.json。
已提取1,135文件、52组资源；不需要重复提取。
资源99 ACT2468引用JDG548，超出本文件0..547，运行时加载上下文仍待解释；
未夹取、删除或补造记录。资源39两条奇数尺寸图块地图尚未实现。
离线受限指令工具仅做核对，不链接进游戏，不含BIOS或硬件模拟。
更多原地址与历史验证见docs下的动作、接触、伤害、普通规则、镜头、KO、效果文档。
当前连续对战说明优先于早期文档中的“停在state8/待接下一局”历史记录。

后续
具体优先级、功能状态和验收条件见 docs/development-plan.txt。
重斩及普通倒地已接入；接下来优先交付基础输入衔接、完整蹲下/站起、66前冲、44后撤、
7/8/9跳跃及落地恢复，再补其余蹲攻和跳攻；独立库通过不计为可玩功能完成。
继续补完整角色更新与动作回调，并将已验证的输入、状态进入和指令消耗接入动作执行；
补全route7/8副作用、异角色登场、声音与舞台，
以及全部角色、招式和系统。
保持所有机制1:1目标；当前可运行的有限对战流程不代表完成整款游戏。

Character select (2026-11-21): the native port always presents the fully unlocked original
select screen: 8 columns x 6 rows (48 cells) including Kim, Rasetsu Galford, Purple Nakoruru,
Poppy, Shikuru & Mamahaha, Chample and PakuPaku, a 47-entry random pool, and Start toggles the
Kuroko view (confirm selects Kuroko). All 49 fighters (0..48) now start and finish matches;
probe_fighter_gaps.py completes 310 of 310 runs for every fighter 0..48. Remaining known gaps
are individual moves and edge cases listed in docs/development-plan.txt.
