// macOS-only secret entry and process handoff. Never print the credential.
import Foundation
import Security
import Darwin

let service = "com.maeum-intake.anthropic"
let account = "ANTHROPIC_API_KEY"
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
    kSecAttrService as String: service, kSecAttrAccount as String: account]
func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8)); exit(1)
}
func checked(_ status: OSStatus) {
    if status != errSecSuccess {
        fail("키체인 작업 실패 (OSStatus \(status)). 키체인 잠금·접근 허용 상태를 확인하세요.")
    }
}
func readSecret() -> Data {
    var q = query
    q[kSecReturnData as String] = true
    q[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    checked(SecItemCopyMatching(q as CFDictionary, &result))
    guard let data = result as? Data, !data.isEmpty else { fail("저장된 키가 없습니다.") }
    return data
}
let args = Array(CommandLine.arguments.dropFirst())
switch args.first {
case "set":
    guard isatty(STDIN_FILENO) == 1 else { fail("실제 터미널에서 실행해 주세요. 파이프 입력은 받지 않습니다.") }
    guard let input = getpass("Claude API 키 (화면에 표시되지 않음): ") else { fail("입력 실패") }
    let count = strlen(input)
    defer { memset(input, 0, count) }
    guard count > 20, count < 4096 else { fail("키 길이를 확인해 주세요. 기존 키는 변경하지 않았습니다.") }
    var data = Data(bytes: input, count: count)
    defer { data.resetBytes(in: 0..<data.count) }
    guard data.starts(with: Data("sk-ant-".utf8)), !data.contains(10), !data.contains(13), !data.contains(32) else {
        fail("Anthropic API 키 형식을 확인해 주세요. 기존 키는 변경하지 않았습니다.")
    }
    let update = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if update == errSecItemNotFound {
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrLabel as String] = "마음 접수 도우미 — Claude API"
        item[kSecAttrSynchronizable as String] = false
        checked(SecItemAdd(item as CFDictionary, nil))
    } else { checked(update) }
    print("macOS 키체인에 저장했습니다. 키 값은 출력하지 않습니다.")
case "status":
    var q = query
    q[kSecReturnAttributes as String] = true
    var result: CFTypeRef?
    let status = SecItemCopyMatching(q as CFDictionary, &result)
    if status == errSecItemNotFound { print("아직 저장되지 않았습니다."); exit(2) }
    checked(status)
    print("키체인 항목이 있습니다. 값 조회·API 유효성 검사는 하지 않았습니다.")
case "run":
    guard args.count >= 3, args[1] == "--" else { fail("사용법: claude_keychain.sh run -- 명령 [인수]") }
    var secret = readSecret()
    defer { secret.resetBytes(in: 0..<secret.count) }
    guard let value = String(data: secret, encoding: .utf8) else { fail("키 형식 오류") }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
    process.arguments = Array(args.dropFirst(2))
    var environment = ProcessInfo.processInfo.environment
    environment[account] = value
    process.environment = environment
    // The child inherits the terminal, not a file containing the key.
    do { try process.run(); process.waitUntilExit(); exit(process.terminationStatus) }
    catch { fail("명령 실행 실패. 실행 파일과 권한을 확인하세요.") }
default:
    fail("사용법: claude_keychain.sh set | status | run -- 명령 [인수]")
}
