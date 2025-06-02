goal:

- substrate chain for development wss:/rpc.hippius.network, for production: ws://127.0.0.1:9944

use python 

using:
- all async.
- one request should not block the program
- comprehensive debuging
- ipfs 
- substrate chain ( just getting the storage to have the profile passing local ipfs node_id as arg ) > ipfsPallet.minerProfile: Bytes
and it return a hex encoded hash of the profile. that we need to decode so we can have the cid. 

- ipfs node is local 
miner should be able to manage the pining, unpinning and dead hash report to validator.

the miner will get there profile from the chain and update the local pinning / unpinning status.


- miner need to have a small database to keep track of all the pinning / unpinning status for easy reporting and management so they don't need to check the local ipfs.


- miner should alsays check if his profile cid change in the chain and update ( they need to pin there profile too.)

- update / create the local database frequently

- pin / unpin and garbage collector based on the local database.


miner should report cid that he can't pin after 5 retry and concatenante all in a json document ( for now let's ceate the document locally, we will send the cid to the chain after)