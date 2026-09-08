"""Enter from the pinned source checkout and place native scratch under the pass."""
import os
from pathlib import Path
from r08_native import require,TARGET,output_path,save,source_record

require(Path.cwd()==TARGET,'service entry cwd must be pinned target')
require(os.environ.get('QWEN_DCU_R08_SITECUSTOMIZE_READY')=='1','runtime overlay import failed before model initialization')
root=output_path(Path(os.environ['QWEN_DCU_R08_PASS_ROOT']))
scratch=output_path(root/'native_working_directory')
scratch.mkdir(exist_ok=False)
save(root/'control/runtime_cwd_binding.json',{'entry_cwd':str(TARGET),'native_output_cwd':str(scratch),'reason':'Native pmc_results text follows process cwd; isolate it before the first model kernel to keep pinned target source clean.','target_source_modified':False})
os.chdir(scratch)
from vllm.entrypoints.cli.main import main
main()
