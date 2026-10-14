import pathlib,shutil,json,configparser
root=pathlib.Path.cwd();repo=root/'engine-samples/Yanxiyimengya--UndertaleMakerX';dst=root/'native-utmx';shutil.copytree(repo/'runtime',dst,ignore=shutil.ignore_patterns('.git','obj','bin'),dirs_exist_ok=True)
shutil.copytree(repo/'examples/Undertale-SansFight',dst/'__data__',ignore=shutil.ignore_patterns('*.import'),dirs_exist_ok=True)
cfg=configparser.ConfigParser(strict=False);cfg.read(repo/'examples/Undertale-SansFight/utmx.cfg');settings={}
for section in ['application','window','player','input']:
 if cfg.has_section(section):
  settings[section]={}
  for k,v in cfg[section].items():
   try:settings[section][k]=json.loads(v)
   except ValueError:pass
settings.setdefault('application',{})['main_script']='main.js'
(dst/'__data__/project_config.json').write_text(json.dumps(settings,indent=2))
