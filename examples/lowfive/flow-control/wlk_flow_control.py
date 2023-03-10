#Usage: mpirun -n $nprocs python wlk_flow_control.py config_file
#config_files= [wilkins_prod_con.yaml, wilkins_prod_2cons.yaml]

import os

#NB: Assuming that user has these env set either i)after spack installation or ii)sourcing vol-plugin.sh explicitly
#os.environ["HDF5_PLUGIN_PATH"] = "/Users/oyildiz/Work/software/lowfive/build/src"
#os.environ["HDF5_VOL_CONNECTOR"] = "lowfive under_vol=0;under_info={};"

if not os.path.exists(os.path.join(os.environ["HDF5_PLUGIN_PATH"], "liblowfive.so")):
    raise RuntimeError("Bad HDF5_PLUGIN_PATH")


import pyhenson as h
import sys

from mpi4py import MPI

import lowfive

serve_counter = 0
def flow_control(vol, comm, intercomms, flowPolicies):
    def bsa_cb():
        global serve_counter
        import sys
        indices = []
        for m in range(len(intercomms)):
            indices.append(m)
        serve = 0
        serve_counter = serve_counter + 1
        for fp in flowPolicies:
            N   = fp[0]
            idx = fp[1]
            if N==-1: #latest
                print("Latest policy for index ", idx)
                probe = intercomms[idx].iprobe(tag=2) #checking whether there are any msgs from consumer
                if probe:
                    serve = 1
                global_serve = comm.allreduce(serve, op=MPI.MAX)
                if global_serve:
                    print("LATEST:serving now: Got msg from con")
                    sys.stdout.flush()
                else:
                    print("LATEST:skipping serving: no msg from con")
                    sys.stdout.flush()
                    indices.remove(idx)
            else:
       	       	print("Some policy for index ", idx)
                if serve_counter % N != 0:
                    indices.remove(idx)
                    print("SOME:skipping serving")
                    sys.stdout.flush()
                else:
                    print("SOME:serving now")
                    sys.stdout.flush()
        print("selected intercomms at counter", serve_counter, ": ", indices)
        sys.stdout.flush()
        return indices

    vol.set_serve_indices(bsa_cb)

#orc@25-01: adding support for defining callback actions externally via YAML file
def import_from(module, name):
    from importlib.util import find_spec
    if not find_spec(module):
        print('%s: No such file exists for the callback actions.' % module, file=sys.stderr)
        exit(1)
    module = __import__(module, fromlist=[name])
    return getattr(module, name)

#orc@22-11: adding the wlk py bindings
import pywilkins as w

world = MPI.COMM_WORLD.Dup()
size = world.Get_size()
rank = world.Get_rank()

#orc@22-11: generating procmap via YAML
config_file = sys.argv[1]
workflow = w.Workflow()
workflow.make_wflow_from_yaml(config_file)
procs_yaml = []
myTasks    = []
puppets    = []
actions    = []
i = 0
for node in workflow.nodes:
    procs_yaml.append((node.func, node.nprocs))
    task_exec = "./" + node.func  + ".hx"; #TODO: This can be an extra field in the YAML file if needed.
    puppets.append((task_exec, node.args))
    if node.actions:
        actions.append((node.func, node.actions))
    #bookkeping of tasks belonging to the execution group
    if rank>=node.start_proc and rank < node.start_proc + node.nprocs:
        myTasks.append(i)
    i = i+1

pm = h.ProcMap(world, procs_yaml)
nm = h.NameMap()

a = MPI._addressof(MPI.COMM_WORLD)
wilkins = w.Wilkins(a,config_file)

#lowfive.create_logger("trace")

#NB: In some cases, L5 comms should only include subset of processes (e.g., rank 0 from LPS)
io_proc = wilkins.is_io_proc()
if io_proc==1:
    comm = w.get_local_comm(wilkins)
    intercomms = w.get_intercomms(wilkins)
    vol = lowfive.DistMetadataVOL(comm, intercomms)
    l5_props = wilkins.set_lowfive()
    execGroup         = []
    from collections import defaultdict
    flowPolicies = defaultdict(list) #key: prodName value: (flowPolicy, intercomm index)
    flow_execGroup    = []
    for prop in l5_props:
        print(prop.filename, prop.dset, prop.producer, prop.consumer, prop.execGroup, prop.memory, prop.prodIndex, prop.conIndex, prop.zerocopy, prop.flowPolicy)
        if prop.memory==1: #TODO: L5 doesn't support both memory and passthru at the moment. This logic might change once L5 supports both modes.
            vol.set_memory(prop.filename, prop.dset)
        else:
            vol.set_passthru(prop.filename, prop.dset)
        if prop.consumer==1 and not any(x in prop.execGroup for x in execGroup): #orc: setting single intercomm per execGroup.
            vol.set_intercomm(prop.filename, prop.dset, prop.conIndex)
            execGroup.append(prop.execGroup)
        if prop.producer==1 and prop.zerocopy==1: #NB: Task can be both producer and consumer.
            vol.set_zerocopy(prop.filename, prop.dset)
        #adding flow control logic
        if prop.producer==1 and prop.flowPolicy!=1 and not any(x in prop.execGroup for x in flow_execGroup): #setting single flow control policy per execGroup
            prodName = prop.execGroup.split(":")[0]
            flow_execGroup.append(prop.execGroup)
            flowPolicies[prodName].append((prop.flowPolicy, prop.prodIndex))

    #if any flow control policies, handling them here.
    for fp in flowPolicies:
        if wilkins.my_node(fp):
            flow_control(vol, comm, intercomms, flowPolicies.get(fp))

    #if any cb actions, setting them here.
    for action in actions:
        if wilkins.my_node(action[0]):
            file_name = action[1][0]
            cb_func   = action[1][1]
            cb =  import_from(file_name, cb_func) 
            cb(vol)  #NB: For more advanced callbacks with args, users would need to write their own wilkins.py 

#TODO: Add the logic for TP mode when L5 supports it (simply iterate thru myTasks)
#print(puppets[myTasks[0]])
myPuppet = h.Puppet(puppets[myTasks[0]][0], puppets[myTasks[0]][1], pm, nm)

wilkins.wait() #consumer waits until the data is ready (i.e., producer's commit function) (if producer or memory mode: void)
myPuppet.proceed()
wilkins.commit() #producer signals that data is ready to use (if consumer or memory mode: void)


