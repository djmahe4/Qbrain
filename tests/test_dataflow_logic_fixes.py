import sys
import os
sys.path.append(os.getcwd())

from brain.dataflow_engine import DataFlowEngine

def test_dataflow_source_attribution():
    """Verify that sources are correctly attributed to variables, not flattened."""
    code = """
    $get_var = $_GET['id'];
    $cookie_var = $_COOKIE['user'];
    $internal_var = 'constant';
    echo $get_var;
    echo $cookie_var;
    echo $internal_var;
    """
    df_engine = DataFlowEngine()
    res = df_engine.analyze_snippet(code, "php")
    
    paths = res["flow_paths"]
    
    # Path for $get_var should have $_GET as source
    get_path = next(p for p in paths if p["variable"] == "$get_var")
    assert get_path["source"] == "$_GET"
    
    # Path for $cookie_var should have $_COOKIE as source
    cookie_path = next(p for p in paths if p["variable"] == "$cookie_var")
    assert cookie_path["source"] == "$_COOKIE"
    
    # Path for $internal_var should NOT be in paths (High-Signal Filter)
    internal_paths = [p for p in paths if p["variable"] == "$internal_var"]
    assert len(internal_paths) == 0

def test_dataflow_inheritance_boundaries():
    """Verify that variable state inheritance respects word boundaries."""
    code = """
    $row = $_GET['id']; // TAINTED
    $other = 'arrow';    // CONSTANT (contains 'row')
    echo $other;
    """
    df_engine = DataFlowEngine()
    res = df_engine.analyze_snippet(code, "php")
    
    assert res["variable_states"]["$other"]["state"] == "CONSTANT"

def test_contextual_sinks():
    """Verify that control flow sinks include context."""
    code = """
    $id = $_GET['id'];
    if ($id == 'admin') {
        echo 'welcome';
    }
    """
    df_engine = DataFlowEngine()
    res = df_engine.analyze_snippet(code, "php")
    
    # Check for contextual sink for $id
    if_paths = [p for p in res["flow_paths"] if p["sink"].startswith("if")]
    print("IF PATHS:", if_paths)
    assert len(if_paths) > 0
    assert "$id == 'admin'" in if_paths[0]["sink"]
    assert if_paths[0]["variable"] == "$id"

def test_quote_escaping_sql_injection():
    """Verify that quote escaping sanitizes only when quoted in query."""
    df_engine = DataFlowEngine()
    
    # Case A: Unquoted integer (Vulnerable)
    code_unquoted = """
    $id = mysqli_real_escape_string($conn, $_GET['id']);
    $query = "SELECT * FROM users WHERE id = $id";
    mysqli_query($conn, $query);
    """
    res_unquoted = df_engine.analyze_snippet(code_unquoted, "php")
    paths_unquoted = res_unquoted["flow_paths"]
    query_paths = [p for p in paths_unquoted if p["variable"] == "$query" and p["sink"] == "mysqli_query"]
    assert len(query_paths) > 0
    assert query_paths[0]["state"] == "TAINTED"

    # Case B: Quoted string (Secure)
    code_quoted = """
    $id = mysqli_real_escape_string($conn, $_GET['id']);
    $query = "SELECT * FROM users WHERE id = '$id'";
    mysqli_query($conn, $query);
    """
    res_quoted = df_engine.analyze_snippet(code_quoted, "php")
    paths_quoted = res_quoted["flow_paths"]
    query_paths_quoted = [p for p in paths_quoted if p["variable"] == "$query" and p["sink"] == "mysqli_query"]
    assert len(query_paths_quoted) > 0
    assert query_paths_quoted[0]["state"] == "SAFE"

def test_cryptographic_hashing_sanitization():
    """Verify that md5/sha1 hashing sanitizes the taint."""
    df_engine = DataFlowEngine()
    code = """
    $pass = $_GET['pass'];
    $hashed = md5($pass);
    $query = "SELECT * FROM users WHERE password = '$hashed'";
    mysqli_query($conn, $query);
    """
    res = df_engine.analyze_snippet(code, "php")
    assert res["variable_states"]["$hashed"]["state"] == "SAFE"

def test_nested_and_recursive_dataflow():
    """Verify that taint propagates recursively through nested assignments."""
    df_engine = DataFlowEngine()
    code = """
    $a = $_GET['id'];
    $b = $a;
    $c = $b;
    $query = "SELECT * FROM users WHERE id = $c";
    mysqli_query($conn, $query);
    """
    res = df_engine.analyze_snippet(code, "php")
    paths = res["flow_paths"]
    query_paths = [p for p in paths if p["variable"] == "$query" and p["sink"] == "mysqli_query"]
    assert len(query_paths) > 0
    assert query_paths[0]["state"] == "TAINTED"

if __name__ == "__main__":
    try:
        test_dataflow_source_attribution()
        test_dataflow_inheritance_boundaries()
        test_contextual_sinks()
        test_quote_escaping_sql_injection()
        test_cryptographic_hashing_sanitization()
        test_nested_and_recursive_dataflow()
        print("Tests finished successfully!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
