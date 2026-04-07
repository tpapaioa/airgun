"""Feature availability registry for airgun based on Satellite version."""

from packaging.version import Version
from widgetastic.utils import ConstructorResolvable, Widgetable


class FeatureDefinition:
    """Definition of a feature and its version-specific availability.

    Attributes:
        name: Unique identifier
        min_version: Minimum Satellite version (inclusive, None = all versions before max_version)
        max_version: Maximum Satellite version (inclusive, None = all versions after min_version)
        description: Human-readable description
        replacement: Name of feature that replaces this feature in later versions (optional)

    Example - Feature removed in 6.19:
        FeatureDefinition(
            name='activation_key.auto_attach',
            max_version='6.18',
            description='Auto-attach functionality',
        )
    """

    def __init__(
        self,
        name,
        min_version=None,
        max_version=None,
        description='',
        replacement=None,
    ):
        self.name = name
        self.min_version = min_version
        self.max_version = max_version
        self.description = description
        self.replacement = replacement if replacement is not None else ''


FEATURE_DEFS = [
    FeatureDefinition(
        name='ui.hosts.legacy_ui_redirect',
        max_version='6.18',
        description='All Hosts page requires redirect to Legacy UI',
    ),
    FeatureDefinition(
        name='ui.contenthost.page',
        max_version='6.18',
        description='ContentHost page exists (later merged into Hosts)',
    ),
    FeatureDefinition(
        name='ui.activationkey.multi_cv_env',
        min_version='6.18',
        description='Multi-CV/env assignment via modal (replaces single assignment)',
    ),
    FeatureDefinition(
        name='ui.activationkey.subscription_attachment',
        max_version='6.18',
        description='Subscription attachment UI (removed along with SCA)',
    ),
    FeatureDefinition(
        name='ui.job_invocation.hosts_table_component_id',
        min_version='6.19',
        description='Job invocation hosts table uses new component ID (job-invocation-hosts-table vs table)',
    ),
]

FEATURE_MATRIX = {fd.name: fd for fd in FEATURE_DEFS}


class VersionFeatureChecker:
    """Check feature availability for a specific Satellite version.

    Instantiate with a Satellite version, then query features with has_feature().
    """

    def __init__(self, satellite_version):
        """Initialize checker with Satellite version.

        Args:
            satellite_version: Satellite version string (e.g., '6.18.0', '6.19')
        """
        self.satellite_version = satellite_version

    def version_match(self, min_version=None, max_version=None):
        """Check whether the given Satellite version falls between the given
        (min_version, max_version) range. The endpoints are inclusive, including
        .z versions.

        For example,
        version='6.18.6', min_version='6.17', max_version='6.18' returns True
        version='6.18', min_version='6.18', max_version='6.19' returns True
        """
        version_obj = Version(self.satellite_version)

        next_version = None
        if max_version:
            v = Version(max_version)
            next_version = f'{v.major}.{v.minor + 1}'

        return not (
            (min_version and version_obj < Version(min_version))
            or (next_version and version_obj >= Version(next_version))
        )

    def has_feature(self, feature_name):
        """Check if feature is available in this Satellite version.

        Args:
            feature_name: Name of the feature

        Returns:
            True if feature is available
        """
        if not (feature := FEATURE_MATRIX.get(feature_name)):
            # Unknown features are assumed unavailable
            return False

        return self.version_match(min_version=feature.min_version, max_version=feature.max_version)


class FeaturePicker(Widgetable, ConstructorResolvable):
    """Widget descriptor that selects between two variants based on feature availability.

    Automatically resolves to the appropriate variant based on the feature's availability
    in the current Satellite version.

    Usage in views:

        class MyView(View):
            # Feature available: use new widget, feature not available: use old widget
            my_widget = FeaturePicker(
                'ui.my_component.new_behavior',
                NewWidget(locator='//div[@id="new"]'),
                OldWidget(locator='//div[@id="old"]'),
            )

            # More compact syntax with positional args
            my_table = FeaturePicker(
                'ui.job_invocation.hosts_table_component_id',
                HostsExpandableTable(component_id='job-invocation-hosts-table'),  # 6.19+
                HostsExpandableTable(component_id='table'),  # 6.18 and earlier
            )

    The descriptor automatically picks the correct widget based on browser.satellite_version
    when accessed from a view instance.
    """

    def __init__(self, feature_name, available, unavailable):
        """Initialize with feature name and two variants.

        Args:
            feature_name: Feature name from VersionFeatureChecker
            available: Widget descriptor for when feature is available
            unavailable: Widget descriptor for when feature is not available
        """
        self.feature_name = feature_name
        self.available = available
        self.unavailable = unavailable

    def __repr__(self):
        return (
            f'{type(self).__name__}({self.feature_name!r}, '
            f'{self.available!r}, {self.unavailable!r})'
        )

    @property
    def child_items(self):
        """Return both variants as child items for widgetastic processing."""
        return [self.available, self.unavailable]

    def pick(self, version):
        """Select the appropriate variant based on feature availability.

        Args:
            version: Version string

        Returns:
            The available or unavailable variant
        """
        if VersionFeatureChecker(version).has_feature(self.feature_name):
            return self.available
        else:
            return self.unavailable

    def __get__(self, o, type=None):
        """Descriptor protocol: resolve to appropriate variant when accessed from instance.

        Args:
            o: View instance (None if accessed from class)
            type: View class

        Returns:
            The appropriate widget variant, instantiated if needed
        """
        if o is None:
            return self

        # Get product version from browser
        result = self.pick(o.browser.satellite_version)

        # If result is a Widgetable, instantiate it
        if isinstance(result, Widgetable):
            return result.__get__(o)
        return result

    def resolve(self, parent_object):
        """Resolve the picker for the given parent object."""
        return self.__get__(parent_object)


class IoPPicker(Widgetable, ConstructorResolvable):
    """Picks between IoP-enabled and IoP-disabled variants.

    Each variant can be a widget, view class, or any other object.

    Usage in a view:

        class MyView(View):
            recommendations = IoPPicker(
                IoPRecommendationstab,
                InsightsTab,
            )

    The picker will instantiate the appropriate tab class based on whether
    IoP is enabled on the Satellite.
    """

    def __init__(self, enabled, disabled):
        """Initialize the picker with two variants.

        Args:
            enabled: Widget descriptor for when IoP is enabled
            disabled: Widget descriptor for when IoP is disabled
        """
        self.enabled = enabled
        self.disabled = disabled

    @property
    def child_items(self):
        """Return both variants as child items for widgetastic processing."""
        return [self.enabled, self.disabled]

    def pick(self, iop_enabled):
        """Pick the appropriate variant based on IoP status.

        :param iop_enabled: Boolean indicating whether IoP is enabled
        :return: The variant object/class for the selected state
        """
        return self.enabled if iop_enabled else self.disabled

    def __get__(self, o, type=None):
        """Descriptor protocol: resolve to appropriate variant when accessed from instance.

        Args:
            o: View instance (None if accessed from class)
            type: View class

        Returns:
            The appropriate widget variant, instantiated if needed
        """
        if o is None:
            return self

        # Get IoP status from browser and pick the variant
        result = self.pick(o.browser.iop_enabled)

        # If result is a Widgetable, instantiate it
        if isinstance(result, Widgetable):
            return result.__get__(o)
        else:
            return result

    def resolve(self, parent_object):
        """Resolve the picker for the given parent object."""
        return self.__get__(parent_object)
