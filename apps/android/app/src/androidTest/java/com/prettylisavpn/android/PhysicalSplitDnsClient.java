package com.prettylisavpn.android;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.net.ConnectivityManager;
import android.net.LinkProperties;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.net.Uri;
import android.os.Binder;
import android.os.Bundle;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Objects;

/** Test-only HTTP client in the instrumentation APK's separate UID. */
public final class PhysicalSplitDnsClient extends ContentProvider {
    private static final String DIRECT = "direct.prettylisa.test";
    private static final String SELECTED = "selected.prettylisa.test";
    private static final String UPLINK = "uplink.prettylisa.test";

    @Override public boolean onCreate() {
        return true;
    }

    @Override public Bundle call(String method, String host, Bundle extras) {
        Context context = Objects.requireNonNull(getContext());
        String targetPackage = context.getPackageName().replaceFirst("\\.test$", "");
        if (!targetPackage.equals(getCallingPackage())) {
            throw new SecurityException("Only the target APK can run the routing fixture");
        }
        boolean ready = "ready".equals(method);
        if (!ready && (!"fetch".equals(method) || !(UPLINK.equals(host) || DIRECT.equals(host) || SELECTED.equals(host)))) {
            throw new IllegalArgumentException("Unknown routing fixture request");
        }
        long caller = Binder.clearCallingIdentity();
        try {
            return fetch(context, host, ready);
        } finally {
            Binder.restoreCallingIdentity(caller);
        }
    }

    private static Bundle fetch(Context context, String host, boolean checkReady) {
        ConnectivityManager manager = context.getSystemService(ConnectivityManager.class);
        Network network = manager.getActiveNetwork();
        NetworkCapabilities capabilities = manager.getNetworkCapabilities(network);
        Bundle result = new Bundle();
        boolean vpn = capabilities != null && capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN);
        result.putBoolean("vpn", vpn);
        if (checkReady) {
            LinkProperties links = manager.getLinkProperties(network);
            result.putBoolean("ready", vpn && links != null && !links.getDnsServers().isEmpty());
            return result;
        }
        boolean expectVpn = !UPLINK.equals(host);
        if (vpn != expectVpn) return result;

        try {
            InetAddress[] addresses = expectVpn ? network.getAllByName(host) : InetAddress.getAllByName(host);
            for (InetAddress address : addresses) {
                byte[] bytes = address.getAddress();
                if (bytes.length != 4 || (expectVpn && !isFake(bytes))) continue;
                result.putBoolean("fake", isFake(bytes));
                try (Socket socket = expectVpn ? network.getSocketFactory().createSocket() : new Socket()) {
                    socket.connect(new InetSocketAddress(address, 18080), 5000);
                    socket.setSoTimeout(5000);
                    String request = "GET /proof.txt HTTP/1.0\r\nHost: " + host + "\r\n\r\n";
                    socket.getOutputStream().write(request.getBytes(StandardCharsets.US_ASCII));
                    BufferedReader input = new BufferedReader(new InputStreamReader(socket.getInputStream(), StandardCharsets.US_ASCII));
                    for (int i = 0; i < 16; i++) {
                        String line = input.readLine();
                        if (line == null) break;
                        result.putBoolean("responded", true);
                        if (line.equals("direct-split-dns-proof")) {
                            result.putBoolean("proof", true);
                            break;
                        }
                    }
                }
                return result;
            }
        } catch (IOException error) {
            result.putString("error", error.getClass().getSimpleName());
        }
        return result;
    }

    private static boolean isFake(byte[] address) {
        return (address[0] & 255) == 198 && (address[1] & 254) == 18;
    }

    @Override public Cursor query(Uri uri, String[] projection, String selection, String[] args, String order) {
        throw new UnsupportedOperationException();
    }
    @Override public String getType(Uri uri) { throw new UnsupportedOperationException(); }
    @Override public Uri insert(Uri uri, ContentValues values) { throw new UnsupportedOperationException(); }
    @Override public int delete(Uri uri, String selection, String[] args) { throw new UnsupportedOperationException(); }
    @Override public int update(Uri uri, ContentValues values, String selection, String[] args) { throw new UnsupportedOperationException(); }
}
