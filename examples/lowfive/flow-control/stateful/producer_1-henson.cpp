#include    <thread>

#include    <diy/master.hpp>
#include    <diy/decomposition.hpp>
#include    <diy/assigner.hpp>
#include    <diy/../../examples/opts.h>

#include    <dlfcn.h>

#include    "prod-con-multidata.hpp"

#include <diy/mpi/communicator.hpp>
using communicator = MPI_Comm;
using diy_comm = diy::mpi::communicator;

void producer1_f (std::string prefix,
                 int threads, int mem_blocks,
                 Bounds domain,
                 int global_nblocks, int dim, size_t local_num_points, int iters, int latest)

{

    fmt::print("Entered producer\n");

    communicator local = MPI_COMM_WORLD;
    diy::mpi::communicator local_(local);

    //orc@31-01: adding looping to test the flow control
    for (size_t i=0; i < iters; i++)
    {
        //emulating fast producer-slow consumer coupling with sleep
        if (latest)
            sleep(5);

        // diy setup for the producer
        diy::FileStorage                prod_storage(prefix);
        diy::Master                     prod_master(local,
                threads,
                mem_blocks,
                &Block::create,
                &Block::destroy,
                &prod_storage,
                &Block::save,
                &Block::load);
        size_t global_num_points = local_num_points * global_nblocks;
        AddBlock                        prod_create(prod_master, local_num_points, global_num_points, global_nblocks);
        diy::ContiguousAssigner         prod_assigner(local_.size(), global_nblocks);
        diy::RegularDecomposer<Bounds>  prod_decomposer(dim, domain, global_nblocks);
        prod_decomposer.decompose(local_.rank(), prod_assigner, prod_create);

        // create a new file and group using default properties
        hid_t file = H5Fcreate("outfile.h5", H5F_ACC_TRUNC, H5P_DEFAULT, H5P_DEFAULT);
        hid_t group = H5Gcreate(file, "/group1", H5P_DEFAULT, H5P_DEFAULT, H5P_DEFAULT);

        std::vector<hsize_t> domain_cnts(DIM);
        for (auto i = 0; i < DIM; i++)
            domain_cnts[i]  = domain.max[i] - domain.min[i] + 1;

        // create the file data space for the global grid
        hid_t filespace = H5Screate_simple(DIM, &domain_cnts[0], NULL);

        // create the grid dataset with default properties
        hid_t dset = H5Dcreate2(group, "grid", H5T_IEEE_F32LE, filespace, H5P_DEFAULT, H5P_DEFAULT, H5P_DEFAULT);

        // write the grid data
        prod_master.foreach([&](Block* b, const diy::Master::ProxyWithLink& cp)
                { b->write_block_grid(cp, dset); });

        // clean up
        H5Dclose(dset);
        H5Sclose(filespace);

        // create the file data space for the particles
        domain_cnts[0]  = global_num_points;
        domain_cnts[1]  = DIM;
        filespace = H5Screate_simple(2, &domain_cnts[0], NULL);

        // create the particle dataset with default properties
        dset = H5Dcreate2(group, "particles", H5T_IEEE_F32LE, filespace, H5P_DEFAULT, H5P_DEFAULT, H5P_DEFAULT);

        // write the particle data
        prod_master.foreach([&](Block* b, const diy::Master::ProxyWithLink& cp)
                { b->write_block_points(cp, dset, global_nblocks); });


        // clean up
        H5Dclose(dset);
        H5Sclose(filespace);
        H5Gclose(group);
        H5Fclose(file);
    }

}

int main(int argc, char* argv[])
{

    int   dim = DIM;

    MPI_Init(NULL, NULL);

    diy::mpi::communicator    world;

    int iters         = 1;
    iters             = atoi(argv[1]);

    int latest         = 0;
    latest             = atoi(argv[2]);

    fmt::print("Halo from Wilkins prod1 with configuration for {} iters and latest/sleep set to {}\n", iters, latest);

    int                       global_nblocks    = world.size();   // global number of blocks
    int                       mem_blocks        = -1;             // all blocks in memory
    int                       threads           = 1;              // no multithreading
    std::string               prefix            = "./DIY.XXXXXX"; // for saving block files out of core
    size_t                    local_npoints     = 100;            // points per block

    // default global data bounds
    Bounds domain { dim };
    for (auto i = 0; i < dim; i++)
    {
        domain.min[i] = 0;
        domain.max[i] = 10;
    }

    // get command line arguments
    using namespace opts;
    Options ops;
    ops
        >> Option('n', "number",    local_npoints,  "number of points per block")
        >> Option('b', "blocks",    global_nblocks, "number of blocks")
        >> Option('t', "thread",    threads,        "number of threads")
        >> Option(     "memblks",   mem_blocks,     "number of blocks to keep in memory")
        >> Option(     "prefix",    prefix,         "prefix for external storage")
        ;
    ops
        >> Option('x',  "max-x",    domain.max[0],  "domain max x")
        >> Option('y',  "max-y",    domain.max[1],  "domain max y")
        >> Option('z',  "max-z",    domain.max[2],  "domain max z")
        ;

    bool verbose, help;
    ops
        >> Option('v', "verbose",   verbose,        "print the block contents")
        >> Option('h', "help",      help,           "show help")
        ;

    if (!ops.parse(argc,argv) || help)
    {
        if (world.rank() == 0)
        {
            std::cout << "Usage: " << argv[0] << " [OPTIONS]\n";
            std::cout << "Generates a grid and random particles in the domain and redistributes them into correct blocks.\n";
            std::cout << ops;
        }
        return 1;
    }

    size_t global_npoints = global_nblocks * local_npoints;         // all block have same number of points

    producer1_f(prefix, threads, mem_blocks, domain, global_nblocks, dim, local_npoints, iters, latest);

    MPI_Finalize();
}
