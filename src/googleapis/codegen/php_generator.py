#!/usr/bin/python2.6
# Copyright 2011 Google Inc. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""PHP library generator.

This module generates a PHP service class from a given Google APIs Discovery
document. The generated PHP code is intended to be used by the Google
APIs PHP Client (http://code.google.com/p/google-api-php-client).

Features:
- Meta classes generated from the schema definition.
- Type hinting in setter methods and api service methods.
- ApiService classes that offer a PHP interface to the API.
- Proper PHPDoc comments for each class and method in the library (FUTURE).
"""

__author__ = 'chirags@google.com (Chirag Shah)'

import collections
import json

from googleapis.codegen import api
from googleapis.codegen import api_library_generator
from googleapis.codegen import data_types
from googleapis.codegen import language_model
from googleapis.codegen import utilities


class PHPGenerator(api_library_generator.ApiLibraryGenerator):
  """The PHP code generator."""

  def __init__(self, discovery, options=None):
    """Create a new PHPGenerator.

    Args:
      discovery: (dict) The discovery document dictionary.
      options: (dict) A dictionary of options to guide the generator's behavior.
    """
    super(PHPGenerator, self).__init__(PHPApi, discovery, 'php',
                                       language_model=PhpLanguageModel(),
                                       options=options)

    # Capitalize the owner since it is used to namespace each generated class.
    owner = self._api.values['owner']
    self._api.values['owner'] = owner[0].upper() + owner[1:]

  def GeneratePackage(self, package):
    """Create all the service classes and bundle them into a single package.

    Args:
      package: (LibraryPackage) output package
    """
    self.AnnotateApiForLanguage(self._api)

    service_file = '%s_%sService.php' % (self._api.values['owner'],
                                         self._api.values['className'])
    out = package.StartFile(service_file)
    self.__GenerateApiClass(out)
    generated = {}
    for schema in self._api.ModelClasses():
      # Skip schemas that refer to others.
      if schema.class_name in generated:
        continue
      self.__GenerateModelClass(out, schema)
      generated[schema.class_name] = True

  def __GenerateApiClass(self, ostream):
    """Generate the main API class."""
    template_path = self.PathToTemplate('api_service_class.tmpl')
    ostream.write(self.RenderTemplate(template_path, {'api': self._api.values}))

  def __GenerateModelClass(self, ostream, schema):
    """Generate a data model class for every schema element."""
    template_path = self.PathToTemplate('_model_class.tmpl')
    ostream.write(self.RenderTemplate(template_path, {
        'api': self._api.values,
        'model': schema.values
        }))

  def AnnotateResource(self, the_api, resource):
    """Add the discovery dictionary as data to each resource.

    Override default implementation.

    Prepend the resource class name to each sub-resource since PHP doesn't
    support nested classes.

    Args:
      the_api: (Api) The API this Resource belongs to.
      resource: (Resource) The Resource to annotate.
    """
    resource.json = json.dumps(_StripResource(resource.raw))
    # Escape stray quotes since it will be used in a PHP function call.
    resource.json = resource.json.replace('\'', '\\\'').replace('{}', '')
    for method in resource.values['methods']:
      self.AnnotateMethod(the_api, method, resource)

    if not resource.GetTemplateValue('phpPropName'):
      resource.SetTemplateValue('phpPropName', resource.values['wireName'])

    for r in resource.values['resources']:
      r.values['className'] = (resource.values['className'] +
                               r.values['className'])
      namespaced = '_'.join((resource.GetTemplateValue('phpPropName'),
                             r.values['wireName']))
      r.SetTemplateValue('phpPropName', namespaced)
      self.AnnotateResource(the_api, r)

  def AnnotateMethod(self, unused_api, method, resource=None):
    """Format service request method parameters.

    Override default implementation.

    Annotates each method parameter with a type hint if possible.
    Adds the postBody parameter if there's a requestType parameter.
    Generates a list of service parameters used by the client library.

    Args:
      unused_api: (Api) The API this Method belongs to.
      method: (Method) The Method to annotate.
      resource: (Resource) The Resource which owns this Method.
    """
    method.json = json.dumps(_StripResource(method.raw))
    # Escape stray quotes since it will be used in a PHP function call.
    method.json = method.json.replace('\'', '\\\'')

    for param in method.parameters:
      self._SetTypeHint(param)

    if method.parameters or method.values.get('requestType'):
      method.SetTemplateValue('hasParams', True)
    method.SetTemplateValue('name', self._ToMethodName(method.values, resource))

  def AnnotateProperty(self, unused_api, prop, unused_schema):
    """Annotate properties with a PHP type hint.

    Overrides default implementation.

    Args:
      unused_api: (Api) The API this Property belongs to.
      prop: (Property) The Property to annotate.
      unused_schema: (Schema) The Schema this Property belongs to.
    """
    if isinstance(prop.data_type, data_types.ArrayDataType):
      prop.SetTemplateValue('dataType', 'array')
    if isinstance(prop.data_type, data_types.MapDataType):
      prop.SetTemplateValue('dataType', 'map')
    self._SetTypeHint(prop)

  def _ToMethodName(self, method, resource):
    """Convert a wire format name into a suitable PHP variable name."""
    s = method['wireName']
    if resource and (s.lower() in PhpLanguageModel.PHP_KEYWORDS):
      s += resource['className']
    return s

  def _SetTypeHint(self, prop):
    """Strip primitive types since PHP doesn't support primitive type hints."""
    code_type = prop.code_type
    if code_type and code_type.lower() in PhpLanguageModel.PHP_TYPES:
      prop.values['typeHint'] = ''
    else:
      prop.values['typeHint'] = '%s_%s ' % (self._api.values['owner'],
                                            code_type)


class PhpLanguageModel(language_model.LanguageModel):
  """A LanguageModel tunded for PHP."""

  _SCHEMA_TYPE_TO_PHP_TYPE = {
      'any': 'object',
      'boolean': 'bool',
      'integer': 'int',
      'long': 'string',  # PHP doesn't support long integers.
      'number': 'double',
      'string': 'string',
      'uint32': 'string',  # PHP doesn't support unsigned integers.
      'uint64': 'string',  # PHP doesn't support unsigned integers.
      'int32': 'int',
      'int64': 'string',  # Size of an integer is platform-dependent.
      'double': 'double',
      'float': 'float',
      }

  # Populated from http://php.net/manual/en/reserved.keywords.php
  PHP_KEYWORDS = frozenset((
      'abstract', 'and', 'array', 'as', 'break',
      'case', 'catch', 'cfunction', 'class', 'clone',
      'const', 'continue', 'declare', 'default', 'do',
      'else', 'elseif', 'enddeclare', 'endfor', 'endforeach',
      'endif', 'endswitch', 'endwhile', 'extends', 'final',
      'for', 'foreach', 'function', 'global', 'goto',
      'if', 'implements', 'interface', 'instanceof', 'list',
      'namespace', 'new', 'old_function', 'or', 'private',
      'protected', 'public', 'static', 'switch', 'throw',
      'try', 'use', 'var', 'while', 'xor',
      ))

  PHP_TYPES = frozenset((
      'bool', 'boolean', 'int', 'integer', 'file', 'float', 'double', 'string',
      'array', 'object',
      'null', 'resource',
      ))

  # We can not create classes which match a PHP keyword or built in object type.
  RESERVED_CLASS_NAMES = PHP_KEYWORDS | PHP_TYPES

  def __init__(self):
    super(PhpLanguageModel, self).__init__(class_name_delimiter='.')

  def GetCodeTypeFromDictionary(self, def_dict):
    """Convert a json primitive type to a suitable PHP type name.

    Overrides the default.

    Args:
      def_dict: (dict) A dictionary describing Json schema for this Property.
    Returns:
      A name suitable for use as a class in PHP.
    """

    # Unique identifier for this schema.
    json_type = def_dict.get('type', 'string')

    # An additional regular expression or key that helps constrain the value.
    # See: http://tools.ietf.org/html/draft-zyp-json-schema-03#section-5.23
    json_format = def_dict.get('format')

    # If we know what to do with this format type, then use native type.
    php_type = (self._SCHEMA_TYPE_TO_PHP_TYPE.get(json_format)
                or self._SCHEMA_TYPE_TO_PHP_TYPE.get(json_type, json_type))
    return php_type

  def CodeTypeForArrayOf(self, type_name):
    """Take a type name and return the syntax for an array of them.

    Override default implementation as a noop. PHP isn't strongly typed.

    Args:
      type_name: (str) A type name.
    Returns:
      A language specific string meaning "an array of type_name".
    """
    return type_name

  def CodeTypeForMapOf(self, type_name):
    """Take a type name and return the syntax for a map of strings of them.

    Override default implementation as a noop. PHP isn't strongly typed.

    Args:
      type_name: (str) A type name.
    Returns:
      The PHP specific string meaning of "a map of type_name".
    """
    return type_name

  def ToMemberName(self, s, unused_api):
    """Convert a wire format name into a suitable PHP variable name.

    Overrides the default.

    Args:
      s: (string) The wire format name of a member variable.
    Returns:
      A name suitable for use as a member in PHP.
    """
    return s.replace('-', '_').replace('.', '_')


class PHPApi(api.Api):
  """An Api with PHP annotations."""

  def __init__(self, discovery_doc, **unused_kwargs):
    """Create a new PHPApi.

    Args:
      discovery_doc: (dict) The discovery document dictionary.
    """
    super(PHPApi, self).__init__(discovery_doc)

  # pylint: disable-msg=W0613
  # The parameter element_type is deliberately unused since PHP doesn't
  # support nested classes.
  def ToClassName(self, s, unused_element, element_type=None):
    """Convert a discovery name to a suitable PHP class name.

    Overrides the default.

    Args:
      s: (string) The wire format name of a class.
      unused_element: (object) The object we need a class name for.
      element_type: (string) The kind of object we need a class name for.
    Returns:
      A name suitable for use as a class in PHP.
    """
    if s.lower() in PhpLanguageModel.RESERVED_CLASS_NAMES:
      # Prepend the service name.
      return utilities.CamelCase(self.values['name']) + utilities.CamelCase(s)
    return utilities.CamelCase(s)

# Properties that should be stripped when serializing parts of the
# discovery document.
_EXTRA_PROPERTIES = ['description', 'enumDescriptions', 'resources', 'pattern',
                     'parameterOrder']


def _StripResource(resource):
  """Return a copy of a resource dict with extraneous properties removed."""
  if not isinstance(resource, dict):
    return resource
  ret = collections.OrderedDict()
  for name, value in resource.iteritems():
    if not name in _EXTRA_PROPERTIES:
      ret[name] = _StripResource(value)
  return ret