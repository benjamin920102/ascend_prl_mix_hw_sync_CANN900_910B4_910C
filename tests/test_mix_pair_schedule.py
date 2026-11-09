#!/usr/bin/env python3
"""Model the CANN MIX 1:2 mode-2 signal protocol (not a device/kernel test)."""
from dataclasses import dataclass
from random import Random
from pathlib import Path

GRID = 20
BUFS = 4


def validate_shape(nbands: int):
    produced = []
    consumed = []
    for lc in range(GRID):
        lane = list(range(lc, nbands, GRID))
        groups = (len(lane) + 1)//2
        assert (len(lane) + 1)//2 == groups
        # Slot is assigned by lane-local iteration, not by global band index.
        for g in range(groups):
            for sub in (0, 1):
                it = 2*g+sub
                if it >= len(lane):
                    continue  # second AIV still participates in hardware handshake
                band = lane[it]
                slot = it % BUFS
                assert slot in (0,1,2,3)
                produced.append(band)
                consumed.append(band)
                if g >= 2:
                    assert (2*(g-2)+sub) % BUFS == slot
    assert sorted(produced) == list(range(nbands))
    assert sorted(consumed) == list(range(nbands))


@dataclass
class Core:
    pos: int = 0
    phase: int = 0
    completed: bool = False


def interleaving_check(nbands: int, lc: int, seed: int):
    """Randomly interleave AIC, AIV0, AIV1 and assert no stale slot reads.

    AIC: wait for ACK of group g-2, write complete group, notify both AIVs.
    AIV: wait for publish, copy group data into private UB, notify AIC,
         optionally hash it before processing next group.
    """
    r = Random(seed)
    lane = list(range(lc, nbands, GRID))
    ng = (len(lane)+1)//2
    aic = Core()
    aivs = [Core(), Core()]
    publish = [0, 0]  # hardware mode-2 counters on two AIVs
    ack = 0  # incremented only when BOTH AIVs set flag, as in mode 2
    acked = [set(), set()]
    shared = [None] * BUFS
    got = []
    steps = 0
    while not (aic.completed and all(c.completed for c in aivs)):
        actions=[]
        if not aic.completed:
            g = aic.pos
            if g >= ng:
                if ack >= ng:
                    actions.append(('aic_finish', None))
            elif g < 2 or ack >= g-1:
                actions.append(('cube', g))
        for sub, av in enumerate(aivs):
            if av.completed: continue
            g = av.pos
            if g >= ng:
                actions.append(('vec_finish', sub))
            elif av.phase == 0 and publish[sub] > g:
                actions.append(('vec_copy', sub))
            elif av.phase == 1:
                actions.append(('vec_ack', sub))
            elif av.phase == 2:
                actions.append(('vec_hash', sub))
        assert actions, (nbands, lc, seed, aic, aivs, publish, ack, shared)
        action, arg = r.choice(actions)
        steps+=1
        assert steps < max(10,ng*25+30)
        if action=='cube':
            g=arg
            for sub in (0,1):
                i=2*g+sub
                if i < len(lane):
                    slot=i%BUFS
                    assert shared[slot] is None, ('unsafe ring reuse', nbands,lc,seed,slot,g,shared)
                    shared[slot]=(g, sub, lane[i])
            for sub in (0,1):
                publish[sub]+=1
            aic.pos+=1
        elif action=='aic_finish':
            aic.completed=True
        elif action=='vec_copy':
            sub=arg
            g=aivs[sub].pos
            it=2*g+sub
            if it<len(lane):
                slot=it%BUFS
                assert shared[slot]==(g,sub,lane[it]), ('corrupt shared slot',nbands,lc,seed,slot)
                got.append(lane[it])
                shared[slot]=None
            aivs[sub].phase=1
        elif action=='vec_ack':
            sub=arg
            g=aivs[sub].pos
            acked[sub].add(g)
            if g in acked[1-sub]:
                ack+=1
            aivs[sub].phase=2
        elif action=='vec_hash':
            sub=arg
            aivs[sub].pos+=1
            aivs[sub].phase=0
        elif action=='vec_finish':
            aivs[arg].completed=True
    assert sorted(got)==lane
    assert ack==ng
    assert shared==[None]*BUFS


def source_checks():
    root=Path(__file__).resolve().parent.parent
    src=(root/'kernel/pearl_hlc2_mix.asc').read_text()
    cmake=(root/'kernel/CMakeLists.txt').read_text()
    assert '__global__ __mix__(1, 2) void pearl_hlc2_mix' in src
    assert '__kfc_workspace__ __gm__ uint8_t* workspace' in src
    assert 'SYNC_AIC_TO_AIV = 8;' in src
    assert 'SYNC_AIV_TO_AIC = 9;' in src
    assert 'CrossCoreSetFlag<0x2, PIPE_FIX>(SYNC_AIC_TO_AIV)' in src
    assert 'CrossCoreSetFlag<0x2, PIPE_MTE2>(SYNC_AIV_TO_AIC)' in src
    assert 'CrossCoreWaitFlag<0x2>(SYNC_AIV_TO_AIC)' in src
    assert 'CrossCoreWaitFlag<0x2>(SYNC_AIC_TO_AIV)' in src
    assert 'static_assert(BUFS == 4,' in src
    assert 'static_assert(VEC2X == 2,' in src
    assert 'g_prodF' not in src and 'g_consF' not in src
    assert 'FlagSpinGE' not in src and 'FlagStore' not in src
    assert 'g_sV' not in src
    assert 'add_library(pearl_hlc2 SHARED pearl_hlc2_mix.asc)' in cmake


if __name__=='__main__':
    source_checks()
    for nbands in range(1,513):
        validate_shape(nbands)
    for nbands in (1,2,3,19,20,21,39,40,41,79,80,81,99,128,129,256,511,512):
        for lc in range(GRID):
            for seed in range(30):
                interleaving_check(nbands, lc, seed)
    print('PASS: source invariants, 512 shapes, 10,800 randomized per-core schedules')
