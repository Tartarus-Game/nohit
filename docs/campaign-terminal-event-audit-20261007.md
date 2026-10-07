# Normal 最终回合结束tick的事件归属

原版 Final 的 EndAttack 内部还会同步创建胜利对话，所以 EndAttack 触发事件本身不是该物理tick的最后一个函数事件。独立observer在看到EndAttack时立即提交回合并清除active；CSV controller在本tick的afterTick完成后才结束持有。两者的round标签边界不同，但事件本身没有矛盾。

源码调用链：

- `Battle.xml:1152` 的 EndAttack 先销毁攻击对象、恢复菜单相关状态并调用ResetVars。
- 同一函数的 `HitAttempts > 22` 分支在 `Battle.xml:1415` 同步调用 `SansText("huff... puff...", "Win1")`。
- `RPGText.xml:171` 的 SansText 在第236行同步调用 TLPause，所以该TLPause仍属于完成Final的物理tick。
- 后续对话完成才调用 `Battle.xml:1477` 的 Win1；它在1482..1483行再次调用 SansText，并指定Win2回调，故会产生另一个较晚的TLPause。
- `Battle.xml:1490` 的 Win2 返回MainMenu。原版没有名为FinalWin的函数。

当前091242完整记录由主任务观测到：Final EndAttack与第一个TLPause同在tick67951；Win1对应的另一个TLPause在tick68070。不能把二者因为都标round24就一起收入或一起排除。

正确匹配区间从该回合实际TLPlay在全局有序事件流中的位置开始，到EndAttack触发tick为止，包含该tick的全部共享事件。依次精确比较controller与独立observer的 `(tick, fn)` 列表，保留重复项与顺序。后续tick的Win/menu回调不属于已完成的CSV controller区间。

独立检查主任务的修复使用该区间，并保留全局事件schema/顺序检查、全部原生tick的HP/KR检查以及所有DamagePlayer参数检查。该变更不能放宽为“只找若干预期事件”，不能删除终帧TLPause，也不能忽略终帧或回合外伤害。

应有的回归边界是：同tick嵌套TLPause准确纳入；晚tick Win1 TLPause排除；终tick的缺失、重复、重排或额外共享事件仍失败；任何正DamagePlayer或HP/KR变化仍失败。记录内容保持原样，仅修复验收器的事件归属口径。
