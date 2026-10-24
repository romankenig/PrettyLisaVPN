package com.prettylisavpn.engine.ipc;
import android.os.IBinder;
interface IEngineControl {
    int protocolVersion();
    String start(String profile, IBinder owner);
    boolean stop();
    String state();
    boolean verify();
}
