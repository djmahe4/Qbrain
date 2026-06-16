import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from brain.dataflow_engine import DataFlowEngine
from brain.parsers.php import extract_dataflow

def test_php_dataflow():
    code = """
<?php
if( array_key_exists( "name", $_GET ) && $_GET[ 'name' ] != NULL ) {
	$name = htmlspecialchars( $_GET[ 'name' ] );
	$html .= "<pre>Hello {$name}</pre>";
}
echo $html;
?>
    """
    df_engine = DataFlowEngine()
    res = df_engine.analyze_snippet(code, "php")
    
    print("Variable States:", res["variable_states"])
    print("Flow Paths:", res["flow_paths"])
    
    # Assertions
    # Assertions
    assert "$name" in res["variable_states"]
    assert res["variable_states"]["$name"]["state"] == "SAFE"
    assert "$html" in res["variable_states"]
    
    # Check paths
    has_echo_sink = any(p["sink"] == "echo" for p in res["flow_paths"])
    assert has_echo_sink

if __name__ == "__main__":
    try:
        test_php_dataflow()
        print("Test passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
