import argparse, json
from pathlib import Path
from .core import load_runtime_config, load_yaml
from .mcp import BridgeCommandTransport, IdeaIndexMCPAdapter, RetrievalStrategy
from .obsidian import ObsidianMCPAdapter, ObsidianContextRetriever, ObsidianExporter
from .store import FactStore
from .validator import IngestionValidator
from .context import ContextBuilder
from .runner import WorkUnitRunner, CommandModelAdapter, OpenAICompatibleHTTPAdapter
from .site import IncrementalSiteBuilder, UCEFWorkbenchServer
from .metadata import MetadataImporter

def framework_root(): return Path(__file__).resolve().parents[1]
def _resolve(v):
    p=Path(v); return p if p.is_absolute() else Path.cwd()/p

def make_components(config_path):
    root=framework_root(); cfg=load_runtime_config(config_path)
    store=FactStore(_resolve((cfg.get("database") or {}).get("path",".ucef/ucef.db")))
    retrieval=None
    idea=cfg.get("idea_mcp") or {}
    if idea.get("transport","none")=="bridge":
        adapter=IdeaIndexMCPAdapter.from_mapping(idea.get("tools") or {}, BridgeCommandTransport(idea.get("bridge_command","")))
        retrieval=RetrievalStrategy(adapter)
    obs_adapter=None; obs_context=None
    obs=cfg.get("obsidian") or {}
    if obs.get("transport","none")=="bridge":
        obs_adapter=ObsidianMCPAdapter.from_mapping(obs.get("tools") or {}, BridgeCommandTransport(obs.get("bridge_command","")))
        obs_context=ObsidianContextRetriever(obs_adapter,cfg)
    builder=ContextBuilder(root,store,cfg,retrieval,obs_context)
    return cfg,store,builder,IngestionValidator(root,store),obs_adapter

def cmd_doctor(a):
    cfg=load_runtime_config(a.config); issues=[]
    root=framework_root()
    for f in ["UCEF_RULES.md","schema.json"]:
        if not (root/f).exists(): issues.append(str(root/f)+" missing")
    for key in ["idea_mcp","obsidian"]:
        x=cfg.get(key) or {}
        if x.get("transport")=="bridge" and not x.get("bridge_command"): issues.append(key+".bridge_command empty")
    print("UCEF doctor:", "OK" if not issues else "WARN")
    for x in issues: print("-",x)
    return 0 if not issues else 1

def cmd_init(a):
    Path(".ucef/contexts").mkdir(parents=True,exist_ok=True)
    _,s,*_=make_components(a.config); s.close(); print("Initialized .ucef/ and SQLite database")

def cmd_build(a):
    _,s,b,_,_=make_components(a.config); sc,wu=load_yaml(a.scenario),load_yaml(a.work_unit)
    s.save_work_unit(wu); s.commit(); text=b.build(sc,wu)
    out=Path(a.output or f".ucef/contexts/{wu['work_unit_id']}.md"); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(text,encoding="utf-8"); print(out); s.close()

def cmd_ingest(a):
    cfg,s,_,v,_=make_components(a.config)
    data=json.loads(Path(a.file).read_text(encoding="utf-8"))
    report=v.ingest(data,a.scenario,a.work_unit)
    site_cfg=cfg.get("site") or {}
    if site_cfg.get("enabled", True) and site_cfg.get("auto_update", True):
        workspace=Path(a.config).resolve().parent
        report["site_update"]=IncrementalSiteBuilder(s,cfg,workspace).update()
    print(json.dumps(report,ensure_ascii=False,indent=2)); s.close()

def cmd_query(a):
    _,s,*_=make_components(a.config); print(json.dumps(s.query(a.scenario,a.type,a.text,a.limit),ensure_ascii=False,indent=2)); s.close()

def cmd_obs(a):
    cfg,s,_,_,adapter=make_components(a.config)
    if adapter is None: raise RuntimeError("Configure obsidian.transport=bridge first")
    print(json.dumps(ObsidianExporter(s,adapter,cfg).sync(a.scenario,a.mode),ensure_ascii=False,indent=2)); s.close()

def cmd_run(a):
    cfg,s,b,v,_=make_components(a.config); sc,wu=load_yaml(a.scenario),load_yaml(a.work_unit); m=cfg.get("model") or {}
    if m.get("mode")=="command": model=CommandModelAdapter(m.get("command",""))
    elif m.get("mode")=="openai_compatible": model=OpenAICompatibleHTTPAdapter(m.get("endpoint",""),m.get("model",""),m.get("api_key_env","UCEF_MODEL_API_KEY"))
    else: raise RuntimeError("Configure model.mode=command or openai_compatible")
    print(json.dumps(WorkUnitRunner(b,v,model).run(sc,wu),ensure_ascii=False,indent=2)); s.close()


def cmd_site(a):
    cfg,s,*_=make_components(a.config)
    workspace=Path(a.config).resolve().parent
    builder=IncrementalSiteBuilder(s,cfg,workspace)
    if a.site_cmd=="build": result=builder.build()
    elif a.site_cmd=="update": result=builder.update()
    elif a.site_cmd=="stats": result=builder.stats()
    elif a.site_cmd=="serve":
        scfg=cfg.get("site") or {}
        host=a.host or scfg.get("host","127.0.0.1"); port=a.port or int(scfg.get("port",8765))
        try: UCEFWorkbenchServer(builder,s,host,port).serve(open_browser=a.open)
        finally: s.close()
        return
    else: raise RuntimeError("Unknown site command")
    print(json.dumps(result,ensure_ascii=False,indent=2)); s.close()

def cmd_metadata(a):
    cfg,s,*_=make_components(a.config)
    importer=MetadataImporter(s)
    if a.metadata_cmd=="import":
        result=importer.import_file(a.file,a.source_type)
        site_cfg=cfg.get("site") or {}
        if site_cfg.get("enabled",True) and site_cfg.get("auto_update",True):
            workspace=Path(a.config).resolve().parent
            result["site_update"]=IncrementalSiteBuilder(s,cfg,workspace).update()
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else: raise RuntimeError("Unknown metadata command")
    s.close()


def main(argv=None):
    p=argparse.ArgumentParser(prog="ucef"); p.add_argument("--config",default=".ucef/config.yaml"); sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("doctor"); x.set_defaults(func=cmd_doctor)
    x=sub.add_parser("init"); x.set_defaults(func=cmd_init)
    x=sub.add_parser("build-context"); x.add_argument("--scenario",required=True); x.add_argument("--work-unit",required=True); x.add_argument("--output"); x.set_defaults(func=cmd_build)
    x=sub.add_parser("ingest"); x.add_argument("--scenario",required=True); x.add_argument("--work-unit",required=True); x.add_argument("--file",required=True); x.set_defaults(func=cmd_ingest)
    x=sub.add_parser("query"); x.add_argument("--scenario"); x.add_argument("--type",choices=["execution_nodes","execution_edges","decisions","data_mutations","interactions"]); x.add_argument("--text"); x.add_argument("--limit",type=int,default=100); x.set_defaults(func=cmd_query)
    x=sub.add_parser("obsidian-sync"); x.add_argument("--scenario",required=True); x.add_argument("--mode",choices=["compact","expanded"]); x.set_defaults(func=cmd_obs)
    x=sub.add_parser("site"); site_sub=x.add_subparsers(dest="site_cmd",required=True)
    y=site_sub.add_parser("build"); y.set_defaults(func=cmd_site)
    y=site_sub.add_parser("update"); y.set_defaults(func=cmd_site)
    y=site_sub.add_parser("stats"); y.set_defaults(func=cmd_site)
    y=site_sub.add_parser("serve"); y.add_argument("--host"); y.add_argument("--port",type=int); y.add_argument("--open",action="store_true"); y.set_defaults(func=cmd_site)
    x=sub.add_parser("metadata"); meta_sub=x.add_subparsers(dest="metadata_cmd",required=True)
    y=meta_sub.add_parser("import"); y.add_argument("--file",required=True); y.add_argument("--source-type",default="DB_METADATA"); y.set_defaults(func=cmd_metadata)
    x=sub.add_parser("run"); x.add_argument("--scenario",required=True); x.add_argument("--work-unit",required=True); x.set_defaults(func=cmd_run)
    a=p.parse_args(argv); return a.func(a)
