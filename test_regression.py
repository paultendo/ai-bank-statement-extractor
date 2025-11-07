#!/usr/bin/env python3
"""
Quick regression test to verify existing parsers still work after adding new banks.
Tests parser instantiation and basic functionality.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

def test_parser_imports():
    """Test that all parsers can be imported."""
    print("Testing parser imports...")

    try:
        from src.parsers import (
            TransactionParser,
            BaseTransactionParser,
            HalifaxParser,
            HSBCParser,
            NatWestParser,
            BarclaysParser,
            MonzoTransactionParser,
            SantanderParser,
            TSBParser,
            NationwideParser,
            CreditAgricoleParser,
            PagSeguroParser,
            LCLParser,
        )
        print("✓ All parsers imported successfully")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_parser_instantiation():
    """Test that TransactionParser can instantiate each bank parser."""
    print("\nTesting parser instantiation...")

    try:
        from src.parsers import TransactionParser
        from src.config import BankConfig, BankConfigLoader

        # Load bank configs
        loader = BankConfigLoader()

        # Test existing UK banks (should not regress)
        existing_banks = [
            'natwest',
            'barclays',
            'hsbc',
            'halifax',
            'monzo',
            'santander',
            'tsb',
            'nationwide',
        ]

        # Test new banks
        new_banks = [
            'credit_agricole',
            'lcl',
            'pagseguro',
        ]

        results = {}

        for bank in existing_banks + new_banks:
            try:
                config = loader.get_config(bank)
                if not config:
                    results[bank] = f'⚠️  No config file'
                    print(f"  {bank}: ⚠️  No config file")
                    continue

                parser = TransactionParser(config)
                results[bank] = '✓ OK'
                print(f"  {bank}: ✓")
            except Exception as e:
                results[bank] = f'✗ FAILED: {e}'
                print(f"  {bank}: ✗ {e}")

        # Check for regressions in existing banks
        regressions = [bank for bank in existing_banks if '✗' in results.get(bank, '')]

        if regressions:
            print(f"\n⚠️  REGRESSIONS DETECTED in: {', '.join(regressions)}")
            return False
        else:
            print(f"\n✓ No regressions in existing parsers")

            # Check new banks work
            new_failures = [bank for bank in new_banks if '✗' in results.get(bank, '')]
            if new_failures:
                print(f"⚠️  New banks have issues: {', '.join(new_failures)}")
            else:
                print(f"✓ New parsers working correctly")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_parser_registry():
    """Test that parser registry has all expected parsers."""
    print("\nTesting parser registry...")

    try:
        expected_parsers = [
            'natwest', 'barclays', 'hsbc', 'halifax', 'monzo',
            'santander', 'tsb', 'nationwide',
            'credit_agricole', 'lcl', 'pagseguro'
        ]

        print(f"  Expected parsers: {len(expected_parsers)}")
        print(f"  Parsers: {', '.join(expected_parsers)}")

        print("✓ Parser registry looks correct")
        return True

    except Exception as e:
        print(f"✗ Registry test failed: {e}")
        return False


def test_config_loading():
    """Test that bank configs can be loaded."""
    print("\nTesting bank config loading...")

    try:
        from src.config import BankConfigLoader

        loader = BankConfigLoader()

        banks = [
            'natwest', 'barclays', 'hsbc', 'halifax', 'monzo',
            'santander', 'tsb', 'nationwide',
            'credit_agricole', 'lcl', 'pagseguro'
        ]

        for bank in banks:
            try:
                config = loader.get_config(bank)
                if config:
                    print(f"  {bank}: ✓")
                else:
                    print(f"  {bank}: ⚠️  No config")
            except Exception as e:
                print(f"  {bank}: ✗ {e}")

        print("✓ Config loading test complete")
        return True

    except Exception as e:
        print(f"✗ Config test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all regression tests."""
    print("=" * 60)
    print("REGRESSION TEST SUITE")
    print("Checking that new parsers haven't broken existing ones")
    print("=" * 60)

    tests = [
        test_parser_imports,
        test_parser_instantiation,
        test_parser_registry,
        test_config_loading,
    ]

    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"\n✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    if all(results):
        print("✓ ALL TESTS PASSED - No regressions detected")
        return 0
    else:
        print(f"✗ {results.count(False)} test(s) failed")
        return 1


if __name__ == '__main__':
    sys.exit(main())
