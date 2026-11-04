import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public protocol HTTPTransport: Sendable {
    func send(_ request: URLRequest) async throws -> (Data, Int)
}

public final class SecureHTTPTransport: NSObject, HTTPTransport, URLSessionTaskDelegate, @unchecked Sendable {
    public func urlSession(_ session: URLSession, task: URLSessionTask,
                           willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                           completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }

    public func send(_ request: URLRequest) async throws -> (Data, Int) {
        let config = URLSessionConfiguration.ephemeral
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.connectionProxyDictionary = [:]
        config.requestCachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        // A new pool is essential after routes change; an old HTTPS socket is not tunnel proof.
        let session = URLSession(configuration: config, delegate: self, delegateQueue: nil)
        defer { session.invalidateAndCancel() }
        do {
            let (data, response) = try await session.data(for: request)
            guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else { throw ClientError("INVALID_RESPONSE") }
            return (data, http.statusCode)
        } catch is CancellationError { throw CancellationError() }
        catch let error as ClientError { throw error }
        catch let error as URLError {
            if error.code == .cancelled { throw CancellationError() }
            throw ClientError(error.code == .timedOut ? "TIMEOUT" : "NETWORK_UNCERTAIN")
        } catch { throw ClientError("NETWORK_UNCERTAIN") }
    }
}

public struct API: Sendable {
    public let base: URL
    let transport: any HTTPTransport
    public init(base: URL, transport: any HTTPTransport = SecureHTTPTransport()) throws {
        guard base.scheme == "https", base.host != nil, base.user == nil, base.password == nil,
              base.query == nil, base.fragment == nil else { throw ClientError("INVALID_API_URL") }
        self.base = base; self.transport = transport
    }
    public func data(_ path: String, method: String = "GET", body: Data? = nil, token: String? = nil,
                     headers: [String: String] = [:], query: [URLQueryItem] = []) async throws -> Data {
        guard !path.contains(".."), !path.contains("://"), !path.contains("?") else { throw ClientError("INVALID_PATH") }
        var components = URLComponents(url: base.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        components.queryItems = query.isEmpty ? nil : query
        var request = URLRequest(url: components.url!)
        request.httpMethod = method; request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("no-store", forHTTPHeaderField: "Cache-Control")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { request.setValue("Bearer " + token, forHTTPHeaderField: "Authorization") }
        for (key, value) in headers { request.setValue(value, forHTTPHeaderField: key) }
        let (data, status) = try await transport.send(request)
        guard (200...299).contains(status) else {
            struct Envelope: Decodable { struct Failure: Decodable { let code: String }; let error: Failure }
            let raw = try? JSONDecoder().decode(Envelope.self, from: data).error.code
            let safe = raw.flatMap { $0.range(of: "^[a-zA-Z0-9_]{1,80}$", options: .regularExpression) != nil ? $0 : nil }
            throw ClientError(safe ?? "HTTP_ERROR", status: status)
        }
        return data
    }
}
