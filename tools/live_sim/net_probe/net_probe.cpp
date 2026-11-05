// Prueba de red para Xenia con el simulador local.
// Llama a las APIs de red y Live del XDK y anota cada resultado en
// net_probe_resultado.txt a traves del simulador, porque Xenia no deja escribir
// en game:\. Contacta con 127.0.0.1 y, para probar Internet, con
// thumbnails.libretro.com.
#include <xtl.h>
#include <xonline.h>
#include <stdio.h>
#include <string.h>

static const char* const SIM_IP = "127.0.0.1";
static const u_short SIM_PORT = 36100;
static int g_ok = 0, g_fail = 0;
static char g_log[8192];

static void Log(const char* text)
{
    OutputDebugStringA(text);
    strcat_s(g_log, text);
}

static void SendResults()
{
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == INVALID_SOCKET) return;
    sockaddr_in a;
    ZeroMemory(&a, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(SIM_PORT);
    a.sin_addr.s_addr = inet_addr(SIM_IP);
    if (connect(s, (sockaddr*)&a, sizeof(a)) == 0) {
        char head[128];
        const int len = (int)strlen(g_log);
        const int n = sprintf_s(head, "POST /probe/resultado HTTP/1.0\r\nContent-Length: %d\r\n\r\n", len);
        send(s, head, n, 0);
        send(s, g_log, len, 0);
        char reply[128];
        recv(s, reply, sizeof(reply), 0);
    }
    closesocket(s);
}

static void Check(const char* name, bool ok, DWORD value)
{
    char line[160];
    sprintf_s(line, "%-4s %-34s 0x%08X\r\n", ok ? "OK" : "FAIL", name, value);
    Log(line);
    if (ok) g_ok++; else g_fail++;
}

// Espera una llamada asincrona y devuelve su resultado final.
static DWORD Finish(XOVERLAPPED* ov, DWORD started)
{
    if (started != ERROR_IO_PENDING && started != ERROR_SUCCESS)
        return started;
    DWORD ignored = 0;
    DWORD result = XGetOverlappedResult(ov, &ignored, TRUE);
    return result == ERROR_SUCCESS ? result : XGetOverlappedExtendedError(ov);
}

#define ASYNC(name, call)                                  \
    do {                                                   \
        XOVERLAPPED ov;                                    \
        ZeroMemory(&ov, sizeof(ov));                       \
        ov.hEvent = CreateEvent(NULL, TRUE, FALSE, NULL);  \
        DWORD r = Finish(&ov, (call));                     \
        CloseHandle(ov.hEvent);                            \
        Check(name, r == ERROR_SUCCESS, r);                \
    } while (0)

static void TestSockets()
{
    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    Check("socket TCP", s != INVALID_SOCKET, (DWORD)s);
    if (s != INVALID_SOCKET) {
        sockaddr_in a;
        ZeroMemory(&a, sizeof(a));
        a.sin_family = AF_INET;
        a.sin_port = htons(SIM_PORT);
        a.sin_addr.s_addr = inet_addr(SIM_IP);
        int c = connect(s, (sockaddr*)&a, sizeof(a));
        Check("connect al simulador", c == 0, c == 0 ? 0 : WSAGetLastError());
        if (c == 0) {
            static const char req[] = "GET /whoami HTTP/1.0\r\nHost: sim\r\n\r\n";
            int sent = send(s, req, sizeof(req) - 1, 0);
            Check("send HTTP", sent == (int)sizeof(req) - 1, sent);
            char buf[512];
            int got = recv(s, buf, sizeof(buf) - 1, 0);
            if (got > 0) buf[got] = 0;
            Check("recv HTTP 200", got > 0 && strstr(buf, " 200 ") != NULL, got);
        }
        closesocket(s);
    }

    // UDP de ida y vuelta en la propia maquina.
    SOCKET u = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
    sockaddr_in local;
    ZeroMemory(&local, sizeof(local));
    local.sin_family = AF_INET;
    local.sin_port = htons(36150);
    local.sin_addr.s_addr = inet_addr(SIM_IP);
    int b = bind(u, (sockaddr*)&local, sizeof(local));
    Check("bind UDP", b == 0, b == 0 ? 0 : WSAGetLastError());
    int sent = sendto(u, "ping", 4, 0, (sockaddr*)&local, sizeof(local));
    Check("sendto UDP", sent == 4, sent);
    fd_set set;
    FD_ZERO(&set);
    FD_SET(u, &set);
    timeval tv = { 2, 0 };
    int ready = select(0, &set, NULL, NULL, &tv);
    Check("select UDP", ready == 1, ready);
    if (ready == 1) {
        char buf[8];
        int got = recvfrom(u, buf, sizeof(buf), 0, NULL, NULL);
        Check("recvfrom UDP", got == 4 && memcmp(buf, "ping", 4) == 0, got);
    }
    closesocket(u);
}

static void TestIdentity()
{
    XNADDR addr;
    DWORD flags = XNET_GET_XNADDR_PENDING;
    for (int i = 0; i < 100 && flags == XNET_GET_XNADDR_PENDING; ++i) {
        flags = XNetGetTitleXnAddr(&addr);
        if (flags == XNET_GET_XNADDR_PENDING) Sleep(50);
    }
    Check("XNetGetTitleXnAddr", flags != XNET_GET_XNADDR_PENDING && flags != XNET_GET_XNADDR_NONE, flags);
    DWORD link = XNetGetEthernetLinkStatus();
    Check("XNetGetEthernetLinkStatus", (link & XNET_ETHERNET_LINK_ACTIVE) != 0, link);

    XUSER_SIGNIN_STATE state = XUserGetSigninState(0);
    Check("XUserGetSigninState (Live)", state == eXUserSigninState_SignedInToLive, (DWORD)state);
    XUID xuid = 0;
    DWORD r = XUserGetXUID(0, &xuid);
    Check("XUserGetXUID", r == ERROR_SUCCESS && xuid != 0, r);
    BOOL allowed = FALSE;
    r = XUserCheckPrivilege(0, XPRIVILEGE_MULTIPLAYER_SESSIONS, &allowed);
    Check("XUserCheckPrivilege multijugador", r == ERROR_SUCCESS && allowed, r);
    Check("XOnlineGetNatType", XOnlineGetNatType() != 0, (DWORD)XOnlineGetNatType());
}

static void TestSession()
{
    const DWORD user = 0;
    const BOOL noPrivate = FALSE;
    ULONGLONG nonce = 0;
    XSESSION_INFO info;
    ZeroMemory(&info, sizeof(info));
    HANDLE session = NULL;
    // Sin datos SPA, XUserSetContext cierra Xenia y la partida cuenta como
    // clasificatoria, asi que la sesion necesita arbitraje.
    const DWORD flags = XSESSION_CREATE_HOST | XSESSION_CREATE_LIVE_MULTIPLAYER_STANDARD |
                        XSESSION_CREATE_USES_ARBITRATION;

    ASYNC("XSessionCreate", XSessionCreate(flags, 0, 4, 0, &nonce, &info, &ov, &session));
    if (session == NULL) return;

    ASYNC("XSessionJoinLocal", XSessionJoinLocal(session, 1, &user, &noPrivate, &ov));
    ASYNC("XSessionModify", XSessionModify(session, flags, 8, 0, &ov));

    static const char qos[] = "net_probe";
    INT q = XNetQosListen(&info.sessionID, (const BYTE*)qos, sizeof(qos), 0,
                          XNET_QOS_LISTEN_ENABLE | XNET_QOS_LISTEN_SET_DATA);
    Check("XNetQosListen", q == 0, (DWORD)q);

    XSESSION_LOCAL_DETAILS details;
    DWORD size = sizeof(details);
    ZeroMemory(&details, size);
    ASYNC("XSessionGetDetails", XSessionGetDetails(session, &size, &details, &ov));

    DWORD needed = 0;
    XSessionSearchByID(info.sessionID, 0, &needed, NULL, NULL);
    Check("XSessionSearchByID tamano", needed > 0, needed);
    if (needed) {
        XSESSION_SEARCHRESULT_HEADER* found = (XSESSION_SEARCHRESULT_HEADER*)malloc(needed);
        ASYNC("XSessionSearchByID", XSessionSearchByID(info.sessionID, 0, &needed, found, &ov));
        free(found);
    }

    ASYNC("XSessionStart", XSessionStart(session, 0, &ov));
    ASYNC("XSessionEnd", XSessionEnd(session, &ov));
    ASYNC("XSessionLeaveLocal", XSessionLeaveLocal(session, 1, &user, &ov));
    ASYNC("XSessionDelete", XSessionDelete(session, &ov));
    XCloseHandle(session);
}

static void TestServices()
{
    DWORD r = XPresenceInitialize(8);
    Check("XPresenceInitialize", r == ERROR_SUCCESS, r);

    DWORD size = 0;
    HANDLE e = NULL;
    r = XFriendsCreateEnumerator(0, 0, 10, &size, &e);
    Check("XFriendsCreateEnumerator", r == ERROR_SUCCESS, r);
    if (r == ERROR_SUCCESS) XCloseHandle(e);

    e = NULL;
    size = 0;
    r = XTitleServerCreateEnumerator(NULL, 10, &size, &e);
    Check("XTitleServerCreateEnumerator", r == ERROR_SUCCESS, r);
    if (r == ERROR_SUCCESS && e) XCloseHandle(e);
}

// Mismos pasos que AdvanXe360 usa para bajar portadas: DNS, socket inseguro y HTTP.
static void TestInternet()
{
    static const char host[] = "thumbnails.libretro.com";
    XNDNS* dns = NULL;
    INT r = XNetDnsLookup(host, NULL, &dns);
    Check("XNetDnsLookup", r == 0 && dns != NULL, (DWORD)r);
    if (r != 0 || dns == NULL) return;
    for (int i = 0; i < 200 && dns->iStatus == WSAEINPROGRESS; ++i)
        Sleep(50);
    const bool resolved = dns->iStatus == 0 && dns->cina > 0;
    Check("DNS resuelto", resolved, (DWORD)dns->iStatus);
    IN_ADDR ip;
    ip.s_addr = resolved ? dns->aina[0].s_addr : 0;
    XNetDnsRelease(dns);
    if (!resolved) return;

    SOCKET s = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    Check("socket Internet", s != INVALID_SOCKET, (DWORD)s);
    if (s == INVALID_SOCKET) return;
    BOOL yes = TRUE;
    r = setsockopt(s, SOL_SOCKET, 0x5801, (const char*)&yes, sizeof(yes));  // SO_MARKINSECURE
    Check("SO_MARKINSECURE", r == 0, r == 0 ? 0 : WSAGetLastError());
    DWORD timeoutMs = 10000;
    setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, (const char*)&timeoutMs, sizeof(timeoutMs));
    setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, (const char*)&timeoutMs, sizeof(timeoutMs));

    sockaddr_in a;
    ZeroMemory(&a, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons(80);
    a.sin_addr = ip;
    r = connect(s, (sockaddr*)&a, sizeof(a));
    Check("connect servidor externo", r == 0, r == 0 ? 0 : WSAGetLastError());
    if (r == 0) {
        char req[160];
        const int n = sprintf_s(req, "HEAD / HTTP/1.0\r\nHost: %s\r\nUser-Agent: net_probe\r\n\r\n", host);
        Check("send HTTP externo", send(s, req, n, 0) == n, (DWORD)n);
        char buf[512];
        const int got = recv(s, buf, sizeof(buf) - 1, 0);
        if (got > 0) buf[got] = 0;
        const bool isHttp = got > 0 && strncmp(buf, "HTTP/1.", 7) == 0;
        Check("recv HTTP externo", isHttp, (DWORD)got);
        if (isHttp) {
            char* end = strstr(buf, "\r\n");
            if (end) *end = 0;
            char line[200];
            sprintf_s(line, "     respuesta: %.150s\r\n", buf);
            Log(line);
        }
    }
    closesocket(s);
}

void __cdecl main()
{
    Log("net_probe: inicio\r\n");

    XNetStartupParams params;
    ZeroMemory(&params, sizeof(params));
    params.cfgSizeOfStruct = sizeof(params);
    params.cfgFlags = XNET_STARTUP_BYPASS_SECURITY;
    INT r = XNetStartup(&params);
    Check("XNetStartup", r == 0, (DWORD)r);
    WSADATA wsa;
    r = WSAStartup(MAKEWORD(2, 2), &wsa);
    Check("WSAStartup", r == 0, (DWORD)r);
    DWORD online = XOnlineStartup();
    Check("XOnlineStartup", online == ERROR_SUCCESS, online);

    TestIdentity();
    TestSockets();
    TestSession();
    TestServices();
    TestInternet();

    char line[64];
    sprintf_s(line, "net_probe: fin OK=%d FAIL=%d\r\n", g_ok, g_fail);
    Log(line);
    SendResults();

    XOnlineCleanup();
    WSACleanup();
    XNetCleanup();
}
