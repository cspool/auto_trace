"""Deterministic gfx936 catalog formulas; unavailable inputs remain null."""
from decimal import Decimal,localcontext
import re
RULE_VERSION='gfx936-native-metric-rules-1'
def ratio(n,d,scale=100):
    if n is None or d in (None,0):return None
    with localcontext() as c:
        c.prec=40
        return str(Decimal(n)*scale/Decimal(d))
def derive(attribute):
    c=attribute['counters'];mode=attribute['counter_mode'];result=[]
    def direct(name):return c.get(name)
    def indices(prefix):
        names=sorted(k for k in c if re.fullmatch(re.escape(prefix)+r'\[\d+\]',k))
        if not names:return None
        values=[c[k] for k in names]
        return None if any(v is None for v in values) else sum(values)
    def total(*prefixes):
        values=[indices(p) for p in prefixes]
        return None if any(v is None for v in values) else sum(values)
    def add(name,value,unit,formula,assumptions='current gfx936 native counters from one physical pass'):
        result.append({'metric_name':name,'value':value,'unit':unit,'formula':formula,'assumptions':assumptions,'availability_state':'available' if value is not None else 'unavailable','availability_reason':'' if value is not None else 'required_native_counter_absent_or_null_or_zero_denominator','evidence_class':'replay_projected','aggregation_rule':'one native dispatch; ratios non-additive; never sum repeated logical family references','rule_version':RULE_VERSION})
    if mode=='pmc':
        add('GPUBusy_pct',ratio(direct('GRBM_GUI_ACTIVE'),direct('GRBM_COUNT')),'percent','100*GRBM_GUI_ACTIVE/GRBM_COUNT')
        add('VALUBusy_pct',ratio(direct('SQ_ACTIVE_INST_VALU'),None if direct('GRBM_GUI_ACTIVE') is None else 320*direct('GRBM_GUI_ACTIVE'),400),'percent','100*SQ_ACTIVE_INST_VALU*4/(320*GRBM_GUI_ACTIVE)','80 compute units and four SIMD units per CU; current source/ABI capability')
        add('LDSBankConflict_pct',ratio(direct('SQ_LDS_BANK_CONFLICT'),None if direct('GRBM_GUI_ACTIVE') is None else 80*direct('GRBM_GUI_ACTIVE')),'percent','100*SQ_LDS_BANK_CONFLICT/(80*GRBM_GUI_ACTIVE)')
        hit=indices('TCC_HIT');miss=indices('TCC_MISS')
        add('L2_hit_count',hit,'native_count','sum(TCC_HIT[i])')
        add('L2_miss_count',miss,'native_count','sum(TCC_MISS[i])')
        add('L2CacheHit_pct',ratio(hit,None if hit is None or miss is None else hit+miss),'percent','100*sum(TCC_HIT)/(sum(TCC_HIT)+sum(TCC_MISS))')
        for k in ['SQ_INSTS_VALU','SQ_INSTS_VMEM_RD','SQ_INSTS_VMEM_WR','SQ_INSTS_LDS','SQ_WAIT_INST_LDS']:
            add(k,direct(k),'native_count',k)
        for key,unit in [('grd','work_items'),('wgr','work_items_per_group'),('lds','bytes_per_workgroup'),('scr','native_scratch_property'),('arch_vgpr','registers_per_work_item'),('accum_vgpr','registers_per_work_item'),('sgpr','registers_per_wave'),('wave_size','work_items_per_wave')]:
            value=attribute.get('native_'+key);add('dispatch_'+key,None if value is None else int(value),unit,'native PMC dispatch property '+key,'dispatch resource property; not achieved occupancy')
        add('achieved_occupancy_pct',None,'percent','unavailable: no proven active-wave/max-wave measurement in bounded native counter modes','register/LDS properties are retained separately; no occupancy estimate substituted')
        result[-1]['availability_reason']='capability_proven_no_achieved_occupancy_counter_in_bounded_native_modes'
    elif mode=='pmc_read':
        req=total('TCC_EA_RDREQ','TCC_EA1_RDREQ');small=total('TCC_EA_RDREQ_32B','TCC_EA1_RDREQ_32B')
        add('read_requests',req,'requests','sum(TCC_EA_RDREQ)+sum(TCC_EA1_RDREQ)')
        add('read_requests_32B',small,'requests','sum(TCC_EA_RDREQ_32B)+sum(TCC_EA1_RDREQ_32B)')
        valid=req is not None and small is not None and 0<=small<=req
        add('native_DRAM_read_bytes',small*32+(req-small)*64 if valid else None,'bytes','32*(sum(TCC_EA_RDREQ_32B)+sum(TCC_EA1_RDREQ_32B))+64*(sum(TCC_EA_RDREQ)+sum(TCC_EA1_RDREQ)-sum(TCC_EA_RDREQ_32B)-sum(TCC_EA1_RDREQ_32B))','gfx936 FETCH_SIZE formula multiplied by 1024; both EA0 and EA1 included')
        add('flat_read_wavefronts',indices('TA_FLAT_READ_WAVEFRONTS'),'native_count','sum(TA_FLAT_READ_WAVEFRONTS[i])')
    elif mode=='pmc_write':
        req=total('TCC_EA_WRREQ','TCC_EA1_WRREQ');large=total('TCC_EA_WRREQ_64B','TCC_EA1_WRREQ_64B')
        add('write_requests',req,'requests','sum(TCC_EA_WRREQ)+sum(TCC_EA1_WRREQ)')
        add('write_requests_64B',large,'requests','sum(TCC_EA_WRREQ_64B)+sum(TCC_EA1_WRREQ_64B)')
        valid=req is not None and large is not None and 0<=large<=req
        add('native_DRAM_write_bytes',(req-large)*32+large*64 if valid else None,'bytes','32*(sum(TCC_EA_WRREQ)+sum(TCC_EA1_WRREQ)-sum(TCC_EA_WRREQ_64B)-sum(TCC_EA1_WRREQ_64B))+64*(sum(TCC_EA_WRREQ_64B)+sum(TCC_EA1_WRREQ_64B))','gfx936 WRITE_SIZE formula multiplied by 1024; atomics classified as writes by catalog')
        add('flat_write_wavefronts',indices('TA_FLAT_WRITE_WAVEFRONTS'),'native_count','sum(TA_FLAT_WRITE_WAVEFRONTS[i])')
    else:raise ValueError(mode)
    return result
