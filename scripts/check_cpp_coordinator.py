"""Exercise the C++ service after a real CMake build, including sanitizer-instrumented builds."""

import os

import grpc

from archon.generated import archon_pb2 as pb
from archon.generated import archon_pb2_grpc as rpc

with grpc.insecure_channel("127.0.0.1:50052") as channel:
    grpc.channel_ready_future(channel).result(timeout=15)
    stub = rpc.ClusterCoordinatorStub(channel)
    auth = (("authorization", f"Bearer {os.environ['ARCHON_API_TOKEN']}"),)
    registered = stub.RegisterNode(pb.NodeInfo(node_id="ci-worker", ip_address="127.0.0.1",
                                               port=50053, cpu_cores=2), metadata=auth, timeout=5)
    assert registered.accepted and registered.term == 1
    heartbeat = stub.SendHeartbeat(pb.HeartbeatRequest(node_id="ci-worker", gpu_utilization=0.2),
                                   metadata=auth, timeout=5)
    assert heartbeat.acknowledged
    missing = stub.SendHeartbeat(pb.HeartbeatRequest(node_id="unknown"), metadata=auth, timeout=5)
    assert not missing.acknowledged
    try:
        stub.RegisterNode(pb.NodeInfo(node_id="unauthenticated"), timeout=5)
        raise AssertionError("unauthenticated request was accepted")
    except grpc.RpcError as error:
        assert error.code() == grpc.StatusCode.UNAUTHENTICATED
print("C++ coordinator registration, heartbeat and authentication passed")
