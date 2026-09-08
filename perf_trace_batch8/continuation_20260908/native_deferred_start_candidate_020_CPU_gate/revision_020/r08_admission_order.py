"""R08-only scheduler admission replay of the recorded R07 per-rank order.

The original eight HTTP requests remain concurrent and byte-identical. This
holds the first measured admissions until all four requests for that rank
arrive, then invokes the unchanged scheduler add_request in observed R07 order.
No forward/model/kernel execution is added. Replay timing is never observed time.
"""
from pathlib import Path
import json,os,time,functools,hashlib
class AdmissionOrder:
    def __init__(self,orders,emit):
        self.orders={int(k):list(v) for k,v in orders.items()};self.byid={x:int(k) for k,v in orders.items() for x in v};self.emit=emit;self.buffer={};self.rank=None;self.released=False
        assert len(self.byid)==8 and set(self.orders)=={0,1} and all(len(v)==4 for v in self.orders.values())
    def stable_id(self,value):
        candidate=value[len('chatcmpl-'):] if value.startswith('chatcmpl-') else value
        for stable in self.byid:
            if candidate==stable:return stable
            if candidate.startswith(stable+'-'):
                suffix=candidate[len(stable)+1:]
                if len(suffix)==8 and all(c in '0123456789abcdef' for c in suffix):return stable
        return None
    def submit(self,request,original):
        stable=self.stable_id(request.request_id)
        if stable is None:return original(request)
        rank=self.byid[stable]
        if self.rank is None:self.rank=rank
        if rank!=self.rank or stable in self.buffer or self.released:raise RuntimeError('R08 measured scheduler admission identity/rank/repeat mismatch')
        self.buffer[stable]=request
        self.emit({'operation':'measured_request_buffered','rank':rank,'stable_request_id':stable,'arrival_ordinal':len(self.buffer),'pid':os.getpid(),'monotonic_ns':time.perf_counter_ns(),'realtime_ns':time.time_ns()})
        if len(self.buffer)<4:return None
        order=self.orders[rank]
        if set(self.buffer)!=set(order):raise RuntimeError('Incomplete exact four-request rank population')
        self.released=True
        for stable in order:original(self.buffer[stable])
        self.emit({'operation':'original_scheduler_admission_released','rank':rank,'request_order':order,'pid':os.getpid(),'monotonic_ns':time.perf_counter_ns(),'realtime_ns':time.time_ns(),'request_objects_modified':False,'extra_requests':0,'extra_model_executions':0})
        return None

def install():
    from r08_native import ROOT,sha,read
    from vllm.v1.core.sched.scheduler import Scheduler
    contract=ROOT/'raw/runtime_tools/replay_admission_order_001.json'
    if sha(contract)!='c66d9a3603f8215db32a5c3f660dc6dd78988917f41954f53e0ccaa0248acf9d':raise RuntimeError('Immutable R07 admission replay contract hash')
    plan=read(contract);source=plan['source_R07_bound_sidecar']
    if sha(source['path'])!=source['sha256']:raise RuntimeError('R07 source order bytes changed')
    original=Scheduler.add_request
    if getattr(original,'_r08_observed_admission_order',False):return
    @functools.wraps(original)
    def add_request(scheduler,request):
        gate=getattr(scheduler,'_r08_admission_order_gate',None)
        if gate is None:
            counter=[0]
            def emit(event):
                counter[0]+=1;out=Path(os.environ['QWEN_DCU_R08_PASS_ROOT'])/'control/admission_order';out.mkdir(exist_ok=True)
                event.update(contract_path=str(contract),contract_sha256='c66d9a3603f8215db32a5c3f660dc6dd78988917f41954f53e0ccaa0248acf9d',replay_diagnostic_only=True)
                path=out/(str(os.getpid())+'.'+str(counter[0]).zfill(3)+'.json')
                with path.open('x') as f:json.dump(event,f,indent=2);f.write('\n')
            gate=AdmissionOrder(plan['orders_by_rank'],emit);scheduler._r08_admission_order_gate=gate
        return gate.submit(request,lambda value:original(scheduler,value))
    add_request._r08_observed_admission_order=True;Scheduler.add_request=add_request
