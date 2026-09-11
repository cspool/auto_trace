#include <rocprofiler/rocprofiler.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <chrono>
#include <thread>
std::vector<hsa_agent_t> agents;
hsa_status_t visit(hsa_agent_t a,void*){hsa_device_type_t t;hsa_agent_get_info(a,HSA_AGENT_INFO_DEVICE,&t);if(t==HSA_DEVICE_TYPE_GPU)agents.push_back(a);return HSA_STATUS_SUCCESS;}
void check(hsa_status_t s,const char* call){if(s!=HSA_STATUS_SUCCESS){const char* msg=nullptr;rocprofiler_error_string(&msg);fprintf(stderr,"%s error %u %s\n",call,s,msg?msg:"");exit(2);}}
uint64_t now(){return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
int main(int argc,char**argv){setbuf(stdout,nullptr);check(hsa_init(),"hsa_init");check(hsa_iterate_agents(visit,nullptr),"agents");int dev=argc>1?atoi(argv[1]):0;int n=argc>2?atoi(argv[2]):20;int ms=argc>3?atoi(argv[3]):20;const char* names[]={"TCC_HIT_sum","TCC_MISS_sum"};rocprofiler_feature_t f[2]{};for(int i=0;i<2;i++){f[i].kind=ROCPROFILER_FEATURE_KIND_METRIC;f[i].name=names[i];}rocprofiler_t*ctx=nullptr;rocprofiler_properties_t props{};props.queue_depth=128;check(rocprofiler_open(agents.at(dev),f,2,&ctx,ROCPROFILER_MODE_STANDALONE|ROCPROFILER_MODE_CREATEQUEUE|ROCPROFILER_MODE_SINGLEGROUP,&props),"open");
for(int j=0;j<n;j++){uint64_t begin=now();check(rocprofiler_start(ctx,0),"start");std::this_thread::sleep_for(std::chrono::milliseconds(ms));check(rocprofiler_stop(ctx,0),"stop");check(rocprofiler_get_data(ctx,0),"get_data");uint64_t end=now();printf("%d,%llu,%llu",dev,(unsigned long long)begin,(unsigned long long)end);for(auto &x:f){double v=x.data.kind==ROCPROFILER_DATA_KIND_INT64?x.data.result_int64:x.data.kind==ROCPROFILER_DATA_KIND_DOUBLE?x.data.result_double:x.data.kind==ROCPROFILER_DATA_KIND_INT32?x.data.result_int32:x.data.result_float;printf(",%d,%.9g",x.data.kind,v);}puts("");check(rocprofiler_reset(ctx,0),"reset");}check(rocprofiler_close(ctx),"close");hsa_shut_down();}
