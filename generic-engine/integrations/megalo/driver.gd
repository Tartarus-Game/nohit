extends Node
var stage
var battle
var soul
var active=false
var tick=0
var pattern=0
var strategy=0
var damage_calls=0
var route=[]
var states=[]
var seen={}
var done=false
var start_hp=0
var replay=[]
var negative=false
var output="user://megalo.json"
func _ready():
 add_to_group("nohit_audit")
 for a in OS.get_cmdline_args():
  if a=="--negative":negative=true
  if a.begins_with("--pattern="):pattern=int(a.substr(10))
  if a.begins_with("--strategy="):strategy=int(a.substr(11))
  if a.begins_with("--out="):output=a.substr(6)
  if a.begins_with("--replay="):
   var f=File.new();f.open(a.substr(9),File.READ);replay=JSON.parse(f.get_as_text()).result.route
 call_deferred("setup")
func setup():
 stage=load("res://Scenes/gameview.tscn").instance()
 add_child(stage)
 yield(get_tree(),"idle_frame")
 var view=stage.find_node("Viewport",true,false)
 view.loadScene(0)
 yield(get_tree().create_timer(1),"timeout")
 battle=view.curscene
 soul=battle.get_node("HeartLayer/PlayerHeart")
 battle.get_node("Hud").menuNo=-1
 start_hp=global.hp
 var attacks=battle.get_node("Attacks")
 attacks.attack=pattern
 attacks.connect("menuEnable",self,"on_done")
 seed(1)
 active=true
 attacks.runAttack()
func on_done():done=true
func on_damage(hp,kr):
 if active and (hp>=0 or kr>0):damage_calls+=1
func _physics_process(_delta):
 if not active:return
 if negative and tick==90:
  var bullets=get_tree().get_nodes_in_group("Bullet")
  if not bullets.empty():
   soul.global_position=bullets[0].get_node("HitBox/Collision").global_position
 if tick>0:states.append({"tick":tick,"x":soul.position.x,"y":soul.position.y,"vx":soul.motion_velocity.x,"vy":soul.motion_velocity.y,"hp":global.hp,"kr":global.kr,"mode":soul.mode,"inv":soul.invCount})
 for bullet in get_tree().get_nodes_in_group("Bullet"):seen[bullet.get_instance_id()]=true
 if damage_calls>0 or global.hp!=start_hp or global.kr>0:
  finish("hit")
  return
 if done:
  finish("native_nohit" if seen.size()>0 else "unknown")
  return
 if tick>=2400:
  finish("unknown")
  return
 var mask=strategy
 if strategy==16:mask=[4,0][int(tick/15)%2]
 if not replay.empty():
  if tick>=replay.size():
   finish("replay_length_mismatch")
   return
  mask=int(replay[tick])
 var names=["ui_left","ui_right","ui_up","ui_down"]
 for i in range(4):
  var event=InputEventAction.new();event.action=names[i];event.pressed=bool(mask&(1<<i));Input.parse_input_event(event)
 route.append(mask)
 tick+=1
func finish(status):
 active=false
 var f=File.new();f.open(output,File.WRITE);f.store_string(JSON.print({"status":status,"pattern":pattern,"strategy":strategy,"ticks":tick,"damage_calls":damage_calls,"hp":global.hp,"kr":global.kr,"entry_hp":start_hp,"attack_completed":done,"observed_bullets":seen.size(),"route":route,"states":states}))
 print("MEGALO_NATIVE ",status," tick=",tick," seen=",seen.size())
 get_tree().quit(0 if status=="native_nohit" else 2)
