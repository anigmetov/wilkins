# Wilkins
Wilkins is an in situ workflow system that enables heterogenous task specification and execution for in situ data processing.
Wilkins provides a data-centric API for defining the workflow graph, creating and launching tasks, establishing communicators between the tasks. 
As its data transport layer, Wilkins uses [LowFive](https://github.com/diatomic/LowFive) library, which is based on the [HDF5](https://www.hdfgroup.org/solutions/hdf5/) data model.
Wilkins allows coupled tasks to communicate both in situ using in-memory data and MPI message passing, and through traditional HDF5 files.
Minimal and often no source-code modification is needed for programs that already use HDF5.
Wilkins supports any directed-graph topology of tasks, including common patterns such as pipeline, fan-in, fan-out, ensembles of tasks, and cycles.

# Installation

You can either install Wilkins using [Spack](https://spack.readthedocs.io/en/latest/) (recommended), or manually.

## Installing with Spack

First, install Spack as explained [here](https://spack.readthedocs.io/en/latest/getting_started.html). Once Spack is
installed and available in your path, clone the Wilkins and LowFive repositories and add them to your local Spack repositories:

```
cd /path/to/wilkins/
git clone https://github.com/orcunyildiz/wilkins.git .
spack repo add /path/to/wilkins/

cd /path/to/lowfive/
git clone https://github.com/diatomic/LowFive.git .
spack repo add /path/to/lowfive/
```

You can confirm that Spack can find Wilkins and LowFive:
```
spack info wilkins
spack info lowfive
```

Then install Wilkins. This could take some time depending on whether you already have a Spack system with MPI
installed. The first time you use Spack, many dependencies need to be satisfied, which by default are installed from
scratch. If you are an experienced Spack user, you can tell Spack to use existing dependencies from
elsewhere in your system.

```
spack install wilkins
```

## Installing manually

### Build dependencies

- C++17
- [MPI](http://www.mpich.org)
- Python 3.8 or higher
- CMake 3.9 or higher
- [LowFive](https://github.com/diatomic/LowFive) 
- [HDF5](https://www.hdfgroup.org/solutions/hdf5/) version 1.14
- [zlib](https://www.zlib.net/)
- [Henson](https://github.com/henson-insitu/henson)

### Building Wilkins

Retrieve the sources of Wilkins (in the current directory, e.g.):
```
git clone https://github.com/orcunyildiz/wilkins.git .
```

Wilkins is built using CMake. Assuming that you created a build directory, then:
```
cd path/to/wilkins/build

cmake /path/to/wilkins/ \
-DCMAKE_CXX_COMPILER=mpicxx \
-DCMAKE_C_COMPILER=mpicc \
-DCMAKE_INSTALL_PREFIX=/path/to/wilkins/install \
-DHENSON_INCLUDE_DIR=/path/to/henson/include \
-DHENSON_LIBRARY=/path/to/henson/build/libhenson.a \
-DHENSON_PMPI_LIBRARY=/path/to/henson/build/libhenson-pmpi-static.a \
-DPYTHON_EXECUTABLE=/path/to/python/bin/python3 \
-DLOWFIVE_INCLUDE_DIR=/path/to/LowFive/install/include \
-DLOWFIVE_LIBRARY=/path/to/LowFive/install/lib/liblowfive.dylib \
-DLOWFIVE_DIST_LIBRARY=/path/to/LowFive/install/lib/liblowfive-dist.a \
-DHDF5_INCLUDE_DIR=/path/to/hdf5/install/include \
-DHDF5_LIBRARY=/path/to/hdf5/install/lib/libhdf5.a \
-DHDF5_HL_LIBRARY=/path/to/hdf5/install/lib/libhdf5_hl.a \
-DZ_LIBRARY=/path/to/zlib/lib/libz.a 

make -j8
make install
```

# Running examples

Wilkins provides several examples of simple workflows. 
With Spack installation, the environment variables required for its LowFive layer are automatically set after doing ``` spack load wilkins```, but with manual installation, set them as follows:

```
export HDF5_VOL_CONNECTOR=lowfive under_vol=0;under_info={};
export HDF5_PLUGIN_PATH=/path/to/lowfive/build/src
```

Assuming Wilkins was installed following the previous instructions, run the following commands:
```
cd /path/to/wilkins/install/examples/lowfive/cycle
./run_cycle.sh

cd /path/to/wilkins/install/examples/lowfive/flow-control/stateful
./run_stateful.sh

```

# Using Wilkins in your own project

To execute the user task codes with Wilkins, first you would need to link them with [Henson](https://github.com/henson-insitu/henson/) as it serves as the execution model of Wilkins. You can refer to the lines 32-46 at Wilkins' main CMake [file](https://github.com/orcunyildiz/wilkins/blob/master/CMakeLists.txt) for this step. 

Second, the task codes need to be compiled as position-independent codes. This requires giving the ```-fPIE``` flag to the compilers. Also, CMake automatically adds this option if ```CMAKE_POSITION_INDEPENDENT_CODE``` is set to ```ON```.

Third, Henson requires some specific linker flags. You would need to add ```-pie -Wl,--export-dynamic``` and ```-Wl,-u,henson_set_contexts,-u,henson_set_namemap``` as linker flags. Please refer to the CMake of the simple examples for this step such as the lines 18-23 at this CMake [file](https://github.com/orcunyildiz/wilkins/blob/master/examples/lowfive/cycle/CMakeLists.txt).

After building the task codes as shared objects and linking them with Henson, you can execute them with the ```wilkins-master.py```, which is the workflow driver code. ```spack load wilkins``` places this driver code in the ```PATH``` automatically. Sample command is given below which uses 4 MPI ranks to execute the workflow description provided in the workflow configuration file. For sample configuration files, please refer to the simple workflow examples provided in this repository.

```
mpirun -n 4 python wilkins-master.py config.yaml

```
