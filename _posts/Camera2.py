# -*- coding: utf-8 -*-
# @Author  : Ree
import random

from mod.client import extraClientApi as clientApi

import pythonScripts.client.ClientUtils as utils
from pythonScripts.client.bean.CameraFrame import Frame, LinearInterpolation, SplineInterpolation
# import pythonScripts.modConfig as config
from pythonScripts.share import StaticConfig, config, VectorUtils

scheduler = utils.getModule(StaticConfig.Module.Scheduler)
system = utils.getSystem()
comp = clientApi.CreateComponent(clientApi.GetLevelId(), "Minecraft", "camera")  # type: CameraComponentClient


def doMove(pos, rot, fov=-1, roll=None):
    # print "doMove", pos, rot, fov
    try:

        if pos is None or rot is None:
            comp.UnLockCamera()
            camera.reset()
        else:

            # print "update camera to ", pos, rot, roll
            # yaw, pitch = rot
            if fov != -1:
                comp.SetFov(fov)
            if roll is not None:
                comp.SetCameraPos(pos)
                comp.SetCameraRotation((rot[0], rot[1], roll))
            else:
                comp.LockCamera(pos, rot)


            x, y, z = pos
            if config.HidePlayer:
                system.NotifyToServer(config.TeleportEvent, {"playerId": clientApi.GetLocalPlayerId(), "pos": (x, -66, z)})

    except:
        pass
        # import logout
        # logout.traceback_print_exc()


def doRelativeMove(pos, rot, entityId, fov=-1):
    if pos is None or pos[0] is None or pos[1] is None or pos[2] is None \
            or rot is None or rot[0] is None or rot[1] is None:
        comp.UnDepartCamera()
        comp.ResetCameraBindActorId()
        comp.SetCameraOffset((0, 0, 0))
        r = utils.getRot(entityId)
        if r is None:
            return
        comp.SetCameraRot(r)
    else:
        p, r = utils.getPosition(entityId)
        if p is None:
            return
        # print "update camera to ", pos, rot
        comp.DepartCamera()
        comp.SetCameraBindActorId(entityId)
        comp.SetCameraOffset(pos)
        comp.SetCameraRot((float(rot[0]), float(rot[1])))
        if fov != -1:
            comp.SetFov(fov)


def fixEulerRotation(first, second, eulerBreak):
    if first == second:
        return first
    normalizedFirst = (first + eulerBreak) % 360.0
    normalizedSecond = (second + eulerBreak) % 360.0
    pathDifference = abs(normalizedSecond - normalizedFirst)
    factor = 1 if normalizedSecond > normalizedFirst else -1
    if pathDifference > 180:
        pathDifference = -1 * (360 - pathDifference)
    return first + factor * pathDifference


class CameraService(object):
    def __init__(self):
        self.tasks = []

    def convert(self, data, enableRoll=False):
        frames = []
        for d in data:
            x, y, z = d.get("pos")
            yaw, pitch = d.get("rot")
            roll = d.get("roll")
            time = d.get("time")
            frames.append({
                "tick": int(time * 3),
                "x": float(x),
                "y": float(y),
                "z": float(z),
                "yaw": float(yaw),
                "pitch": float(pitch),
                "roll": float(roll) if enableRoll and roll is not None else None,
                "fov": float(d.get("fov", -1))
            })
        newData = {
            "perspect": 1,
            "spline": config.Spline,
            "frames": frames,
        }
        self.runMovie(newData)

    def runMovie(self, data):
        if len(self.tasks) > 0:
            self.clearTasks()
        print "onMovie", data
        relative = data.get("relative", False)
        endless = data.get("endless", False)
        perspect = data.get("perspect", -1)
        entityId = data.get("entityId", clientApi.GetLocalPlayerId())
        lockYaw = data.get("lockYaw", True)
        lockPitch = data.get("lockPitch", True)
        spline = data.get("spline", True)
        if perspect >= 0:
            utils.setPerspective(perspect)
        if lockYaw:
            utils.lockCameraYaw()
        if lockPitch:
            utils.lockCameraPitch()
        frames = data.get("frames", [])
        lastFrame = None
        input = []
        for frame in frames:
            tick = frame.get("tick", 0)
            x = frame.get("x", 0)
            y = frame.get("y", 0)
            z = frame.get("z", 0)
            yaw = frame.get("yaw", 0)
            pitch = frame.get("pitch", 0)
            fov = frame.get("fov", -1)
            roll = frame.get("roll", None)
            if relative and perspect > 0:
                yaw = 90 - yaw
            if lastFrame is not None:
                if tick < lastFrame.tick:
                    print "帧错误！没有按照时间排序！"
                    return
            lastFrame = Frame(tick, x, y, z, fixEulerRotation(lastFrame.yaw if lastFrame is not None else 0, yaw, 180), fixEulerRotation(lastFrame.pitch if lastFrame is not None else 0, pitch, 0), fov=fov, roll=roll)
            input.append(lastFrame)
        output = (SplineInterpolation(input) if spline and len(input) > 1 else LinearInterpolation(input)).prepare()
        print "total frames: %d" % len(output)
        # print output
        if relative:
            for frame in output:
                taskId = scheduler.runFuncTaskLater(frame.tick, doRelativeMove, (frame.x, frame.y, frame.z), (frame.yaw, frame.pitch), entityId, fov=frame.fov, roll=frame.roll)
                self.tasks.append(taskId)
        else:
            for frame in output:
                taskId = scheduler.runFuncTaskLater(frame.tick, doMove, (frame.x, frame.y, frame.z), (frame.yaw, frame.pitch), fov=frame.fov, roll=frame.roll)
                self.tasks.append(taskId)

        if not endless:

            if relative:
                taskId = scheduler.runFuncTaskLater(lastFrame.tick + 1, doRelativeMove, None, None, None)
                self.tasks.append(taskId)
            else:
                taskId = scheduler.runFuncTaskLater(lastFrame.tick + 1, doMove, None, None)
                self.tasks.append(taskId)
            if perspect >= 0:
                taskId = scheduler.runFuncTaskLater(lastFrame.tick + 1, utils.releasePerspective, )
                self.tasks.append(taskId)
            if lockYaw or lockPitch:
                taskId = scheduler.runFuncTaskLater(lastFrame.tick + 1, utils.releaseCameraLock, )
                self.tasks.append(taskId)
            taskId = scheduler.runFuncTaskLater(lastFrame.tick + 1, system.BroadcastEvent, config.MovieFinishEvent, {"id": data.get("id")})
            self.tasks.append(taskId)
        scheduler.runFuncTaskLater(lastFrame.tick + 1, self.clearTasks, )

    def makeShake(self, force, long):
        pos, face = utils.getCameraPosition()
        cameraRot = VectorUtils.vector2angle(face)

        def tick(pos, rot):
            if pos is None or rot is None:
                comp.UnLockCamera()
            else:
                comp.LockCamera(pos, rot)

        import math
        x = VectorUtils.findVelocity(face, 0)
        y = VectorUtils.findVelocity(face, math.pi / 2)
        for time in range(long):
            vx = VectorUtils.multiple(x, random.random() * force * 2 - force)
            vy = VectorUtils.multiple(y, random.random() * force * 2 - force)

            force *= 0.9
            # print pos, vx, vy
            scheduler.runFuncTaskLater(time, tick, VectorUtils.add(pos, VectorUtils.add(vx, vy)), cameraRot)
        scheduler.runFuncTaskLater(long + 1, tick, None, cameraRot)

    def clearTasks(self):
        for task in self.tasks:
            scheduler.cancelTaskById(task)
        del self.tasks[:]

    def reset(self):
        self.clearTasks()
        doMove(None, None)
        doRelativeMove(None, None, clientApi.GetLocalPlayerId())
        utils.releasePerspective()
        utils.releaseCameraLock()


camera = CameraService()


