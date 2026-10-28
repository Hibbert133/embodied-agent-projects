"""Complete the previously required global fixed-gain controls before collection."""
from pathlib import Path
ROOT=Path(r'C:/Users/Administrator/Desktop/embodied-agent-projects')
replacements={
 'src/analysis/occam_qualification_statistics_v1.py': [('==1404','==1566'),('all1404','all1566')],
 'src/analysis/occam_qualification_statistics_audit_v1.py': [('==1404','==1566'),('all_executions=1404','all_executions=1566'),('all26','all29'),(']*7',']*10'),('all seven fixed primary','all ten fixed primary')],
 'scripts/report_occam_reference_qualification_v1.py': [('all_1560_allocated','all_1740_allocated'),('all_1404_qualified','all_1566_qualified'),('all_26_programs','all_29_programs'),('all_468_task','all_522_task'),('1560','1740'),('1404','1566'),('NATIVE156','NATIVE174'),('全部程序','全部程序'),('七个','十个'),('26程序','29程序'),('780000','870000'),('79560','88740'),('43680000','48720000')],
 'tests/test_occam_own_history_qualification_v1.py': [('[156,1404]','[174,1566]'),('len(actor.PROGRAMS),26','len(actor.PROGRAMS),29'),('1560*51','1740*51'),('1560*28000','1740*28000'),("len(result['primary']),7","len(result['primary']),10")],
}
for name,pairs in replacements.items():
    p=ROOT/name;value=p.read_text(encoding='utf8')
    for before,after in pairs:value=value.replace(before,after)
    compile(value,name,'exec');p.write_text(value,encoding='utf8',newline='\n')
p=ROOT/'docs/protocols/occam_reference_qualification_v1_zh.md';s=p.read_text(encoding='utf8')
for before,after in [('固定前缀为携带积分的RAW PI0.5','学习程序与同前缀参考的前缀为携带积分的RAW PI0.5'),
 ('共24程序，再加原DIRECT_C8和MOVE_INTEGRAL，共26。','共24程序，再加三条全时固定PI及原DIRECT_C8和MOVE_INTEGRAL，共29。\n全时固定PI从第0步保持0.125／2／8秒；全时0.5秒与PI_0500__CONTINUE\n是同一程序，别名GLOBAL_PI_0500只引用已有执行，不重复采集或计费。'),
 ('156例','174例'),('1404例','1566例'),('|NATIVE|156|78000|156|7956|4368000|','|NATIVE|174|87000|174|8874|4872000|'),
 ('|QUAL|1404|702000|1404|71604|39312000|','|QUAL|1566|783000|1566|79866|43848000|'),
 ('|合计|1560|780000|1560|79560|43680000|','|合计|1740|870000|1740|88740|48720000|'),
 ('各上限780000','各上限870000'),('四种固定PI__CONTINUE、ERM_ADAPT__CONTINUE、DIRECT_C8、','四种同前缀固定PI__CONTINUE、三条新增全时固定PI、ERM_ADAPT__CONTINUE、DIRECT_C8、'),
 ('七个差','十个差'),('七比较','十比较'),('所有26程序','所有29程序')]:
    s=s.replace(before,after)
p.write_text(s,encoding='utf8',newline='\n')
print('global fixed controls and complete budget/statistical scope added before any allocation',flush=True)
